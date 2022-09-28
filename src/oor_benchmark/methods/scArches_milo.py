import milopy
import numpy as np
import scanpy as sc
import scvi
from anndata import AnnData

from ._latent_embedding import embedding_scArches


def run_milo(
    adata_design: AnnData,
    query_group: str,
    reference_group: str,
    sample_col: str = "sample_id",
    annotation_col: str = "cell_annotation",
    design: str = "~ is_query",
):
    """Test differential abundance analysis on neighbourhoods with Milo.

    Parameters:
    ------------
    adata_design : AnnData
        AnnData object of disease and reference cells to compare
    query_group : str
        Name of query group in adata_design.obs['dataset_group']
    reference_group : str
        Name of reference group in adata_design.obs['dataset_group']
    sample_col : str
        Name of column in adata_design.obs to use as sample ID
    annotation_cols : str
        Name of column in adata_design.obs to use as annotation
    design : str
        Design formula for differential abundance analysis (the test variable is always 'is_query')
    """
    milopy.core.make_nhoods(adata_design, prop=0.1)
    milopy.core.count_nhoods(adata_design, sample_col=sample_col)
    milopy.utils.annotate_nhoods(adata_design[adata_design.obs["dataset_group"] == reference_group], annotation_col)
    adata_design.obs["is_query"] = adata_design.obs["dataset_group"] == query_group
    milopy.core.DA_nhoods(adata_design, design=design)


def scArches_milo(
    adata: AnnData,
    embedding_reference: str = "atlas",
    diff_reference: str = "ctrl",
    sample_col: str = "sample_id",
    annotation_col: str = "cell_annotation",
    signif_alpha: float = 0.1,
    outdir: str = None,
    harmonize_output: bool = True,
    milo_design: str = "~ is_query",
    **kwargs,
):
    r"""Worflow for OOR state detection with scArches embedding and Milo differential analysis.

    Parameters:
    ------------
    adata: AnnData
        AnnData object of disease and reference cells to compare.
        If `adata.obsm['X_scVI']` is already present, the embedding step is skipped
    embedding_reference: str
        Name of reference group in adata.obs['dataset_group'] to use for latent embedding
    diff_reference: str
        Name of reference group in adata.obs['dataset_group'] to use for differential abundance analysis
    sample_col: str
        Name of column in adata.obs to use as sample ID
    annotation_col: str
        Name of column in adata.obs to use as annotation
    signif_alpha: float
        FDR threshold for differential abundance analysi (default: 0.1)
    outdir: str
        path to output directory (default: None)
    milo_design: str
        design formula for differential abundance analysis (the test variable is always 'is_query')
    \**kwargs:
        extra arguments to embedding_scArches
    """
    # Subset to datasets of interest
    adata = adata[adata.obs["dataset_group"].isin([embedding_reference, diff_reference, "query"])].copy()

    # for testing (remove later?)
    if "X_scVI" not in adata.obsm:
        if outdir is not None:
            try:
                # if os.path.exists(outdir + f"/model_{embedding_reference}/") and os.path.exists(outdir + f"/model_fit_query2{embedding_reference}/"):
                vae_ref = scvi.model.SCVI.load(outdir + f"/model_{embedding_reference}/")
                vae_q = scvi.model.SCVI.load(outdir + f"/model_fit_query2{embedding_reference}/")
                adata.obsm["X_scVI"] = np.vstack(
                    [vae_q.get_latent_representation(), vae_ref.get_latent_representation()]
                )
            except (ValueError, FileNotFoundError):
                embedding_scArches(
                    adata, ref_dataset=embedding_reference, outdir=outdir, batch_key="sample_id", **kwargs
                )
        else:
            embedding_scArches(adata, ref_dataset=embedding_reference, outdir=outdir, batch_key="sample_id", **kwargs)

    # remove embedding_reference from anndata if not needed anymore
    if diff_reference != embedding_reference:
        adata = adata[adata.obs["dataset_group"] != embedding_reference].copy()

    # Make KNN graph for Milo neigbourhoods
    n_controls = adata[adata.obs["dataset_group"] == diff_reference].obs[sample_col].unique().shape[0]
    n_querys = adata[adata.obs["dataset_group"] == "query"].obs[sample_col].unique().shape[0]
    sc.pp.neighbors(adata, use_rep="X_scVI", n_neighbors=(n_controls + n_querys) * 5)

    run_milo(adata, "query", diff_reference, sample_col=sample_col, annotation_col=annotation_col, design=milo_design)

    # Harmonize output
    if harmonize_output:
        sample_adata = adata.uns["nhood_adata"].T.copy()
        sample_adata.var["OOR_score"] = sample_adata.var["logFC"].copy()
        sample_adata.var["OOR_signif"] = (
            ((sample_adata.var["SpatialFDR"] < signif_alpha) & (sample_adata.var["logFC"] > 0)).astype(int).copy()
        )
        sample_adata.varm["groups"] = adata.obsm["nhoods"].T
        adata.uns["sample_adata"] = sample_adata.copy()
    return adata


def scArches_atlas_milo_ctrl(adata: AnnData, **kwargs):
    """Worflow for OOR state detection with scArches embedding and Milo differential analysis - ACR design."""
    return scArches_milo(adata, embedding_reference="atlas", diff_reference="ctrl", **kwargs)


def scArches_atlas_milo_atlas(adata: AnnData, **kwargs):
    """Worflow for OOR state detection with scArches embedding and Milo differential analysis - AR design."""
    return scArches_milo(adata, embedding_reference="atlas", diff_reference="atlas", **kwargs)


def scArches_ctrl_milo_ctrl(adata: AnnData, **kwargs):
    """Worflow for OOR state detection with scArches embedding and Milo differential analysis - CR design."""
    return scArches_milo(adata, embedding_reference="ctrl", diff_reference="ctrl", **kwargs)
