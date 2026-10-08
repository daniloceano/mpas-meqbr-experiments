#!/usr/bin/env python
"""Create context figures used by the Petrobras technical report.

The report needs three pictures before it can discuss skill: what the baseline
mesh resolves, what EXP01 changes at the lower boundary, and how EXP02 moves
the lateral relaxation zone away from the area of interest. A fourth figure
locates the observation network.

Only mesh/static files and cached field means are read. No MPAS history is
opened, so this is safe to run while an integration is active.

Outputs:
    figures/report/experimental_design_ctl_mesh.png
    figures/report/experimental_design_exp01_sst.png
    figures/report/experimental_design_exp02_mesh.png
    figures/report/validation_network.png
    figures/report/validation_cells.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from netCDF4 import Dataset
import numpy as np
from scipy.spatial import ConvexHull
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import mesh, plotting  # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT  # noqa: E402

ANALYSIS_EXTENT = (-46.5, -33.5, -7.5, 1.0)


def read_mesh(path: Path) -> dict[str, np.ndarray]:
    with Dataset(path) as ds:
        lat = np.rad2deg(np.asarray(ds.variables["latCell"][:]))
        lon = np.rad2deg(np.asarray(ds.variables["lonCell"][:]))
        area = np.asarray(ds.variables["areaCell"][:])
        bdy = np.asarray(ds.variables["bdyMaskCell"][:])
    # Centre-to-centre spacing for an equivalent regular hexagonal cell.
    spacing = np.sqrt(2.0 * area / np.sqrt(3.0)) / 1000.0
    return {"lat": lat, "lon": lon, "spacing": spacing, "bdy": bdy}


def read_mesh_topology(path: Path) -> dict[str, np.ndarray]:
    """Cell centres, land mask and Voronoi vertices needed for site zooms."""
    with Dataset(path) as ds:
        out = {
            "lat": np.rad2deg(np.asarray(ds.variables["latCell"][:])),
            "lon": np.rad2deg(np.asarray(ds.variables["lonCell"][:])),
            "vertex_lat": np.rad2deg(np.asarray(ds.variables["latVertex"][:])),
            "vertex_lon": np.rad2deg(np.asarray(ds.variables["lonVertex"][:])),
            "vertices_on_cell": np.asarray(ds.variables["verticesOnCell"][:]),
            "n_edges": np.asarray(ds.variables["nEdgesOnCell"][:]),
            "landmask": np.asarray(ds.variables["landmask"][:]),
        }
    out["lon"] = ((out["lon"] + 180.0) % 360.0) - 180.0
    out["vertex_lon"] = ((out["vertex_lon"] + 180.0) % 360.0) - 180.0
    return out


def local_polygons(data: dict[str, np.ndarray], indices: np.ndarray):
    polygons, cells = [], []
    for cell in indices:
        n_edges = int(data["n_edges"][cell])
        vertices = data["vertices_on_cell"][cell, :n_edges] - 1
        if np.any(vertices < 0):
            continue
        polygons.append(np.column_stack([
            data["vertex_lon"][vertices], data["vertex_lat"][vertices]
        ]))
        cells.append(int(cell))
    return polygons, np.asarray(cells, dtype=int)


def gridlines(ax):
    gl = ax.gridlines(draw_labels=True, linewidth=0.35, color="0.55",
                      alpha=0.55, linestyle=":")
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 8}
    gl.ylabel_style = {"size": 8}


def add_inmet_markers(ax, cfg, transform, *, size: float = 34) -> None:
    """Add primary INMET stations without labels to avoid map clutter."""
    stations = [
        station for station in cfg.surface["stations"]
        if station["kind"] in cfg.surface["primary_kinds"]
    ]
    if not stations:
        return
    ax.scatter(
        [station["lon"] for station in stations],
        [station["lat"] for station in stations],
        marker="^", s=size, c="#f4a261", edgecolors="black", linewidths=0.45,
        zorder=8, transform=transform,
    )


def observation_legend_handles() -> list[Line2D]:
    return [
        Line2D([0], [0], marker="^", color="none", markerfacecolor="#f4a261",
               markeredgecolor="black", markeredgewidth=0.45, markersize=7,
               label="Estações INMET (10 m)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="none",
               markeredgecolor="black", markersize=7, label="P0 — LiDAR"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="none",
               markeredgecolor="black", markersize=7, label="LPI — LiDAR"),
    ]


def plot_mesh_resolution(cfg, experiment: str, mesh_name: str, output: Path) -> None:
    import cartopy.crs as ccrs

    data = read_mesh(cfg.runs_root / f"{mesh_name}.static.nc")
    buffered = experiment == "EXP02"
    extent = (-61.5, -26.0, -14.0, 13.0) if buffered else (-56.2, -31.4, -9.0, 8.0)
    vmax = 32.0 if buffered else 6.0

    fig, ax = plt.subplots(figsize=(10.5, 6.2),
                           subplot_kw={"projection": ccrs.PlateCarree()})
    sc = ax.scatter(data["lon"], data["lat"], c=data["spacing"], s=1.0,
                    cmap="turbo_r", vmin=4.0, vmax=vmax, linewidths=0,
                    rasterized=True, transform=ccrs.PlateCarree())
    relaxation = data["bdy"] > 0
    if relaxation.any():
        ax.scatter(data["lon"][relaxation], data["lat"][relaxation],
                   s=1.1 if buffered else 0.8, c="#262626", alpha=0.72,
                   linewidths=0, rasterized=True,
                   transform=ccrs.PlateCarree())
    plotting.coastlines(ax, resolution="10m", lw=0.65)
    plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree(), fontsize=9)
    add_inmet_markers(ax, cfg, ccrs.PlateCarree())
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    gridlines(ax)
    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", pad=0.08,
                      fraction=0.055, extend="max")
    cb.set_label("Espaçamento horizontal equivalente entre centros de célula (km) — vermelho = menor")
    if buffered:
        title = ("EXP02 — malha com zona de transição\n"
                 "~5 km na região de interesse, aumentando gradualmente até 32 km")
    else:
        title = "CTL — malha de referência quase uniforme"
    ax.set_title(title, fontsize=13, pad=12,
                 color=plotting.EXPERIMENT_COLORS[experiment])
    handles = observation_legend_handles()
    if relaxation.any():
        handles.append(Line2D([0], [0], marker="o", color="none",
                              markerfacecolor="#262626", markeredgecolor="none",
                              markersize=6, label="Células de relaxação lateral"))
    ax.legend(handles=handles, loc="lower left", fontsize=8)
    plotting.provenance_footer(
        fig,
        f"Fonte: {mesh_name}.static.nc | espaçamento calculado a partir de areaCell "
        "assumindo célula hexagonal equivalente | turbo invertido: vermelho = menor "
        "espaçamento | círculos/quadrados: LiDAR; triângulos: INMET",
        fontsize=6.5, layout=False)
    fig.savefig(output, dpi=300)
    plt.close(fig)


def plot_sst_delta(cfg, output: Path) -> None:
    import cartopy.crs as ccrs

    ctl_path = REPO_ROOT / "results/fields/CTL_2021_fields.nc"
    exp_path = REPO_ROOT / "results/fields/EXP01_2021_fields.nc"
    with xr.open_dataset(ctl_path) as ctl, xr.open_dataset(exp_path) as exp:
        if (ctl.attrs["window_start"], ctl.attrs["window_end"]) != (
                exp.attrs["window_start"], exp.attrs["window_end"]):
            raise ValueError("CTL and EXP01 SST means use different windows")
        lat = ctl["lat"].values
        lon = ctl["lon"].values
        delta = exp["mean_sst"].values - ctl["mean_sst"].values
        ocean = (ctl["landmask"].values == 0) & (exp["landmask"].values == 0)
        window = (ctl.attrs["window_start"][:10], ctl.attrs["window_end"][:10],
                  int(ctl.attrs["n_hours"]))

    tri, idx = mesh.triangulation(lat, lon, ANALYSIS_EXTENT)
    values = np.where(ocean[idx], delta[idx], np.nan)
    fig, ax = plt.subplots(figsize=(10.5, 6.2),
                           subplot_kw={"projection": ccrs.PlateCarree()})
    pc = ax.tripcolor(tri, values, cmap="RdBu_r", vmin=-10, vmax=10,
                      shading="gouraud", rasterized=True,
                      transform=ccrs.PlateCarree())
    plotting.coastlines(ax, resolution="10m", lw=0.7)
    plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree(), fontsize=9)
    add_inmet_markers(ax, cfg, ccrs.PlateCarree())
    ax.set_extent(ANALYSIS_EXTENT, crs=ccrs.PlateCarree())
    gridlines(ax)
    cb = fig.colorbar(pc, ax=ax, orientation="horizontal", pad=0.08,
                      fraction=0.055, extend="both")
    cb.set_label("Diferença da SST média: EXP01 − CTL (K)")
    ax.set_title("EXP01 — efeito introduzido pela atualização diária da SST",
                 fontsize=13, pad=12, color=plotting.EXPERIMENT_COLORS["EXP01"])
    ax.legend(handles=observation_legend_handles(), loc="lower left", fontsize=8)
    plotting.provenance_footer(
        fig,
        f"Campos médios de {window[0]} a {window[1]} ({window[2]} saídas horárias) | "
        "limites de cor saturados em ±10 K para tornar visíveis diferenças oceânicas "
        "menores | círculos/quadrados: LiDAR; triângulos: INMET",
        fontsize=6.5, layout=False)
    fig.savefig(output, dpi=300)
    plt.close(fig)


def hull_polygon(data: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    points = np.column_stack([data["lon"], data["lat"]])
    sample = points[::10]
    hull = ConvexHull(sample)
    poly = sample[np.r_[hull.vertices, hull.vertices[0]]]
    return poly[:, 0], poly[:, 1]


def plot_validation_network(cfg, output: Path) -> None:
    import cartopy.crs as ccrs

    ctl = read_mesh(cfg.runs_root / "meqbr_05km.static.nc")
    buf = read_mesh(cfg.runs_root / "meqbr_05km_buf.static.nc")
    ctl_lon, ctl_lat = hull_polygon(ctl)
    buf_lon, buf_lat = hull_polygon(buf)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.8),
                             subplot_kw={"projection": ccrs.PlateCarree()})
    ax = axes[0]
    ax.plot(buf_lon, buf_lat, color=plotting.EXPERIMENT_COLORS["EXP02"],
            lw=1.8, ls="--", transform=ccrs.PlateCarree(), label="Domínio EXP02")
    ax.plot(ctl_lon, ctl_lat, color=plotting.EXPERIMENT_COLORS["CTL"],
            lw=2.0, transform=ccrs.PlateCarree(), label="Domínio CTL/EXP01")
    ax.add_patch(Rectangle((ANALYSIS_EXTENT[0], ANALYSIS_EXTENT[2]),
                           ANALYSIS_EXTENT[1] - ANALYSIS_EXTENT[0],
                           ANALYSIS_EXTENT[3] - ANALYSIS_EXTENT[2],
                           fill=False, ec="#f4a261", lw=2.0,
                           transform=ccrs.PlateCarree(), label="Zoom da validação"))
    plotting.coastlines(ax, resolution="10m", lw=0.65)
    ax.set_extent((-64, -23, -17, 16), crs=ccrs.PlateCarree())
    gridlines(ax)
    ax.set_title("Domínios de modelagem", fontsize=11)
    ax.legend(loc="lower left", fontsize=8)

    ax = axes[1]
    plotting.coastlines(ax, resolution="10m", lw=0.8)
    short_names = {
        "81752099999": "Parnaíba",
        "81715099999": "São Luís",
        "81758099999": "Fortaleza",
        "81798099999": "Jaguaruana",
        "81835099999": "Apodi",
        "81754099999": "Sobral",
    }
    for station in cfg.surface["stations"]:
        if station["kind"] not in cfg.surface["primary_kinds"]:
            continue
        ax.scatter(station["lon"], station["lat"], marker="^", s=62,
                   c="#e76f51", ec="white", lw=0.8, zorder=7,
                   transform=ccrs.PlateCarree())
        ax.annotate(short_names.get(station["id"], station["name"]),
                    (station["lon"], station["lat"]), xytext=(5, 5),
                    textcoords="offset points", fontsize=8, zorder=8,
                    bbox=dict(fc="white", ec="none", alpha=0.75, pad=1),
                    transform=ccrs.PlateCarree())
    for key, site in cfg.sites.items():
        marker = plotting.SITE_MARKERS[key]
        ax.scatter(site.lon, site.lat, marker=marker, s=72, facecolors="none",
                   edgecolors="black", linewidths=1.7, zorder=8,
                   transform=ccrs.PlateCarree())
        offset = (-8, -18) if key == "P0" else (8, -16)
        align = "right" if key == "P0" else "left"
        ax.annotate(f"{key} — LiDAR", (site.lon, site.lat), xytext=offset,
                    textcoords="offset points", fontsize=8.5, fontweight="bold",
                    ha=align, zorder=8,
                    bbox=dict(fc="white", ec="none", alpha=0.8, pad=1),
                    transform=ccrs.PlateCarree())
    ax.set_extent(ANALYSIS_EXTENT, crs=ccrs.PlateCarree())
    gridlines(ax)
    ax.set_title("Rede observacional usada na validação", fontsize=11)
    ax.legend(handles=[
        Line2D([0], [0], marker="^", color="none", markerfacecolor="#e76f51",
               markeredgecolor="white", markersize=9, label="INMET automática (10 m)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="none",
               markeredgecolor="black", markersize=8, label="P0 — LiDAR flutuante"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="none",
               markeredgecolor="black", markersize=8, label="LPI — LiDAR fixo"),
    ], loc="lower left", fontsize=8)
    fig.suptitle("Margem Equatorial Brasileira (MEqBr): domínio e pontos de validação",
                 fontsize=14, y=0.99)
    plotting.provenance_footer(
        fig,
        "Estações INMET automáticas obtidas via NOAA ISD; aeroportos/sinópticas não "
        "são mostradas porque têm papel suplementar. Contornos derivados das duas malhas MPAS.",
        fontsize=6.5, layout=False)
    fig.savefig(output, dpi=300)
    plt.close(fig)


def plot_validation_cells(cfg, output: Path) -> None:
    """Show the exact MPAS cells paired with P0/LPI on both meshes."""
    import cartopy.crs as ccrs

    mesh_names = ["meqbr_05km", "meqbr_05km_buf"]
    labels = ["CTL/EXP01 — malha ~4,6 km", "EXP02 — malha com buffer"]
    datasets = {
        name: read_mesh_topology(cfg.runs_root / f"{name}.static.nc")
        for name in mesh_names
    }

    fig = plt.figure(figsize=(14.5, 7.6))
    grid = fig.add_gridspec(2, 3, width_ratios=[1.35, 1, 1],
                            wspace=0.22, hspace=0.28)
    ax_main = fig.add_subplot(grid[:, 0], projection=ccrs.PlateCarree())
    base = datasets["meqbr_05km"]
    ocean = base["landmask"] == 0
    ax_main.scatter(base["lon"][ocean], base["lat"][ocean], s=0.35,
                    c="#8ecae6", linewidths=0, rasterized=True,
                    transform=ccrs.PlateCarree())
    ax_main.scatter(base["lon"][~ocean], base["lat"][~ocean], s=0.35,
                    c="#cbbf9b", linewidths=0, rasterized=True,
                    transform=ccrs.PlateCarree())
    plotting.coastlines(ax_main, resolution="10m", lw=0.7)
    margin_deg = 0.18
    for key, site in cfg.sites.items():
        ax_main.plot(site.lon, site.lat, marker="*", ms=10, mfc="black",
                     mec="white", mew=0.8, zorder=8,
                     transform=ccrs.PlateCarree())
        ax_main.annotate(key, (site.lon, site.lat), xytext=(7, 5),
                         textcoords="offset points", fontsize=9,
                         fontweight="bold",
                         bbox=dict(fc="white", ec="none", alpha=0.8, pad=1),
                         transform=ccrs.PlateCarree(), zorder=9)
        ax_main.add_patch(Rectangle(
            (site.lon - margin_deg, site.lat - margin_deg),
            2 * margin_deg, 2 * margin_deg, fill=False, ec="black", lw=1.3,
            transform=ccrs.PlateCarree(), zorder=7))
    add_inmet_markers(ax_main, cfg, ccrs.PlateCarree(), size=30)
    ax_main.set_extent(ANALYSIS_EXTENT, crs=ccrs.PlateCarree())
    gridlines(ax_main)
    ax_main.set_title("Posição dos LiDARs na malha de referência", fontsize=11)
    ax_main.legend(handles=[
        Line2D([0], [0], marker="*", color="none", markerfacecolor="black",
               markeredgecolor="white", markersize=10, label="LiDAR"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor="#f4a261",
               markeredgecolor="black", markeredgewidth=0.45, markersize=7,
               label="Estações INMET (10 m)"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#8ecae6",
               markeredgecolor="none", markersize=8, label="célula oceânica"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#cbbf9b",
               markeredgecolor="none", markersize=8, label="célula terrestre"),
    ], loc="lower left", fontsize=8)

    for row, (site_key, site) in enumerate(cfg.sites.items()):
        for column, (mesh_name, label) in enumerate(zip(mesh_names, labels), start=1):
            ax = fig.add_subplot(grid[row, column])
            data = datasets[mesh_name]
            local = np.flatnonzero(
                (np.abs(data["lat"] - site.lat) <= margin_deg * 1.15)
                & (np.abs(data["lon"] - site.lon) <= margin_deg * 1.15))
            polygons, cells = local_polygons(data, local)
            facecolors = np.where(data["landmask"][cells] == 0,
                                  "#cfe8f3", "#cbbf9b")
            ax.add_collection(PolyCollection(
                polygons, facecolors=facecolors, edgecolors="0.48",
                linewidths=0.65, zorder=1))
            match = mesh.nearest_cells(
                data["lat"], data["lon"], site.lat, site.lon,
                landmask=data["landmask"], ocean_only=True, k=1)[0]
            matched = np.flatnonzero(cells == match.index)
            if len(matched):
                ax.add_collection(PolyCollection(
                    [polygons[int(matched[0])]], facecolors="none",
                    edgecolors="black", linewidths=2.5, zorder=4))
            ax.plot(match.lon, match.lat, marker="x", ms=8, mew=1.8,
                    color="black", zorder=5)
            ax.plot(site.lon, site.lat, marker="*", ms=14, mfc="#e63946",
                    mec="white", mew=0.9, zorder=6)
            ax.annotate(
                f"{site_key}\ncentro da célula: {match.distance_km:.1f} km",
                (site.lon, site.lat), xytext=(8, 8), textcoords="offset points",
                fontsize=8, fontweight="bold",
                bbox=dict(fc="white", ec="0.35", alpha=0.9, pad=2), zorder=7)
            ax.set_xlim(site.lon - margin_deg, site.lon + margin_deg)
            ax.set_ylim(site.lat - margin_deg, site.lat + margin_deg)
            ax.set_aspect("equal")
            ax.set_xlabel("Longitude (°)")
            ax.set_ylabel("Latitude (°)")
            ax.set_title(label, fontsize=9.5)
            ax.grid(alpha=0.2, lw=0.45)

    fig.suptitle("Células MPAS usadas na comparação com os LiDARs P0 e LPI",
                 fontsize=14, y=0.995)
    plotting.provenance_footer(
        fig,
        "Fonte: arquivos static.nc das duas malhas | estrela vermelha: posição do "
        "LiDAR | contorno preto e x: célula oceânica mais próxima e seu centro | "
        "polígonos: células Voronoi nativas do MPAS. A distância quantifica o "
        "deslocamento entre o instrumento pontual e o valor de grade usado na validação. "
        "Triângulos mostram as estações INMET sem rótulos.",
        fontsize=6.7, layout=False)
    fig.savefig(output, dpi=300)
    plt.close(fig)


def main() -> int:
    cfg = load_config()
    plotting.use_style(scale=1.1)
    out_dir = REPO_ROOT / "figures" / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        out_dir / "experimental_design_ctl_mesh.png",
        out_dir / "experimental_design_exp01_sst.png",
        out_dir / "experimental_design_exp02_mesh.png",
        out_dir / "validation_network.png",
        out_dir / "validation_cells.png",
    ]
    plot_mesh_resolution(cfg, "CTL", "meqbr_05km", outputs[0])
    plot_sst_delta(cfg, outputs[1])
    plot_mesh_resolution(cfg, "EXP02", "meqbr_05km_buf", outputs[2])
    plot_validation_network(cfg, outputs[3])
    plot_validation_cells(cfg, outputs[4])
    for path in outputs:
        print(f"-> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
