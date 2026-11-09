"""Scientific colour maps (Crameri 2018, v8) resampled to 64 stops.

Source: cmcrameri 1.9 LUTs, https://www.fabiocrameri.ch/colourmaps/ ;
selection guided by https://dominicroye.github.io/color-for-geoscience/ .
Perceptually uniform and colour-vision-deficiency friendly. Embedded so the
pipeline does not depend on cmcrameri being installed on every host.

Crameri, F. (2018). Scientific colour maps. Zenodo. doi:10.5281/zenodo.1243862
"""

from __future__ import annotations

import matplotlib
from matplotlib.colors import LinearSegmentedColormap

LUTS: dict[str, list[str]] = {
    "batlow": [
        "#011959", "#051f5a", "#08255b", "#0b2b5c", "#0d315d", "#0e365e", "#0f3b5f", "#103f60",
        "#114360", "#124761", "#134b61", "#154f62", "#175362", "#195762", "#1c5a62", "#1f5d61",
        "#236060", "#27635f", "#2c665d", "#31695b", "#376b58", "#3c6d56", "#426f52", "#48714f",
        "#4f734c", "#557548", "#5b7745", "#627941", "#687b3e", "#6f7d3a", "#767f37", "#7d8134",
        "#868330", "#8e852e", "#95872c", "#9d892b", "#a58b2c", "#ad8c2d", "#b58e30", "#bd8f34",
        "#c49138", "#cb923e", "#d29343", "#d9954a", "#e09651", "#e69858", "#eb9a60", "#f09c69",
        "#f49f72", "#f8a17b", "#faa485", "#fca78e", "#fdaa97", "#fdaea2", "#fdb1ab", "#fdb4b4",
        "#fdb7bc", "#fdbac4", "#fdbccd", "#fcbfd6", "#fcc3df", "#fbc6e8", "#fbc9f1", "#faccfa"],
    "lipari": [
        "#031326", "#05182d", "#061d35", "#07223c", "#092844", "#0b2d4b", "#0e3353", "#13385a",
        "#183e61", "#1e4368", "#25486d", "#2f4e73", "#385277", "#3f5679", "#47587a", "#4d5a7b",
        "#535c7a", "#585d7a", "#5d5d79", "#625e78", "#665e77", "#6b5f76", "#705f74", "#745f73",
        "#795f72", "#7e6071", "#83606f", "#89606e", "#8e616c", "#94616b", "#9a6169", "#a06268",
        "#a86266", "#ae6364", "#b56363", "#bc6461", "#c36660", "#ca675f", "#d06a5e", "#d76d5e",
        "#dd715f", "#e17660", "#e57b62", "#e88165", "#e98768", "#ea8d6b", "#ea926e", "#e99872",
        "#e89d76", "#e7a279", "#e6a77d", "#e6ac81", "#e5b186", "#e5b88c", "#e6bd92", "#e7c398",
        "#e9c99f", "#ebcfa7", "#edd5af", "#f0dbb7", "#f3e1c0", "#f6e8c9", "#faeed1", "#fdf5da"],
    "devon": [
        "#2c1a4c", "#2b1d50", "#2b2154", "#2b2558", "#2a295b", "#2a2c5f", "#293063", "#293467",
        "#29386a", "#283b6e", "#283f72", "#274478", "#27487c", "#274d81", "#275186", "#28558b",
        "#295990", "#2b5d96", "#2d609c", "#3063a2", "#3266a7", "#3669ad", "#3a6cb2", "#3e6fb8",
        "#4472bd", "#4a76c3", "#517ac8", "#597dcc", "#6181d0", "#6985d4", "#7188d8", "#798cdb",
        "#8290df", "#8a94e1", "#9197e4", "#989be7", "#9e9ee9", "#a4a2eb", "#aaa5ed", "#aea9ee",
        "#b2adef", "#b6b0f0", "#bab3f1", "#bdb7f1", "#c0baf2", "#c3bef3", "#c6c1f3", "#cac5f4",
        "#cdc8f5", "#d0ccf5", "#d3cff6", "#d6d3f7", "#dad6f7", "#dedbf8", "#e1def9", "#e4e2fa",
        "#e8e5fa", "#ebe9fb", "#eeedfc", "#f2f0fc", "#f5f4fd", "#f8f8fe", "#fcfbfe", "#ffffff"],
    "lajolla": [
        "#191900", "#1d1b02", "#201c04", "#241d06", "#271e08", "#2b200a", "#2f210d", "#33220f",
        "#372411", "#3c2614", "#412716", "#482a1a", "#4e2c1d", "#542e20", "#5b3023", "#613227",
        "#69352b", "#70372e", "#783932", "#7f3c36", "#873e3a", "#8f403d", "#984240", "#a04442",
        "#a84645", "#b14847", "#b94a48", "#c04d49", "#c7504b", "#cd534c", "#d2584c", "#d75c4d",
        "#db634e", "#dd684e", "#df6d4f", "#e0724f", "#e17750", "#e37c50", "#e48150", "#e58651",
        "#e68b51", "#e68f52", "#e79452", "#e89852", "#e99d53", "#eaa253", "#eba653", "#ecab54",
        "#edb054", "#eeb555", "#efba56", "#f1c058", "#f2c55b", "#f4cd61", "#f5d369", "#f7d971",
        "#f8df7c", "#fae587", "#fbea93", "#fcef9f", "#fdf3ab", "#fef7b6", "#fefbc0", "#fffecb"],
    "vik": [
        "#001261", "#011865", "#021f69", "#02256d", "#022b71", "#023175", "#023779", "#033e7d",
        "#034481", "#034a85", "#055189", "#08598f", "#0e6093", "#156798", "#1e6f9d", "#2877a2",
        "#337fa8", "#3f87ad", "#4b90b3", "#5798b9", "#64a0be", "#71a8c4", "#7db0c9", "#8ab8ce",
        "#97c0d4", "#a3c7d9", "#b0cfde", "#bdd6e3", "#c9dde7", "#d5e3e9", "#e0e6e9", "#e8e7e5",
        "#eee3dc", "#eeddd3", "#edd5c8", "#eacebd", "#e7c6b2", "#e4bea8", "#e0b69d", "#ddae93",
        "#daa688", "#d69f7e", "#d39774", "#d0906b", "#cd8961", "#ca8258", "#c77b4f", "#c47445",
        "#c16d3c", "#be6533", "#ba5e2a", "#b55521", "#af4c18", "#a5400f", "#9c3709", "#942f06",
        "#8b2706", "#832106", "#7c1b06", "#741506", "#6d1007", "#670a07", "#600408", "#590008"],
    "roma": [
        "#7e1700", "#822204", "#862c06", "#8b3409", "#8f3c0c", "#92440f", "#964b12", "#995215",
        "#9d5818", "#a05f1b", "#a3651e", "#a76d21", "#aa7324", "#ad7a27", "#b0802b", "#b4872f",
        "#b78e33", "#ba9538", "#be9d3e", "#c1a545", "#c5ac4c", "#c8b455", "#cbbc5f", "#cec46a",
        "#d0cc75", "#d2d381", "#d2d98d", "#d2de98", "#d0e3a3", "#cde6ad", "#c9e9b6", "#c4eabe",
        "#bdeac6", "#b5eacc", "#ade8d0", "#a4e5d3", "#9be2d5", "#90ded7", "#86d9d7", "#7bd4d7",
        "#71ced6", "#67c7d5", "#5dc1d3", "#55bad1", "#4db3cf", "#46accc", "#40a6ca", "#3a9fc7",
        "#3698c5", "#3292c2", "#2f8cbf", "#2c85bd", "#297fba", "#2677b7", "#2471b4", "#226ab1",
        "#2064ae", "#1e5dab", "#1b56a8", "#194fa5", "#1548a2", "#11409f", "#0b399c", "#033198"],
    "bilbao": [
        "#4c0001", "#520509", "#580b10", "#5e1115", "#64161a", "#691b1f", "#6e2024", "#732529",
        "#78292f", "#7d2e34", "#823239", "#88383f", "#8c3c43", "#904148", "#94464b", "#974a4f",
        "#994f51", "#9b5353", "#9d5754", "#9e5b56", "#9f5e56", "#a06257", "#a16558", "#a26859",
        "#a36b59", "#a46e5a", "#a4715b", "#a5745b", "#a6775c", "#a77a5d", "#a87d5d", "#a8805e",
        "#a9845f", "#aa865f", "#ab8960", "#ac8d61", "#ad9061", "#ae9362", "#af9664", "#b09a66",
        "#b19e68", "#b3a26d", "#b5a772", "#b7ab79", "#b9ae80", "#bbb287", "#bdb58e", "#bfb795",
        "#c0ba9c", "#c2bca3", "#c3bfa9", "#c5c1af", "#c7c3b4", "#c9c7bc", "#cbcac1", "#cecdc7",
        "#d2d2ce", "#d7d7d4", "#dddddb", "#e3e3e2", "#eaeae9", "#f1f1f0", "#f8f8f8", "#ffffff"],
    "navia": [
        "#031327", "#04182e", "#051c36", "#05213e", "#052546", "#062a4e", "#062f56", "#07345e",
        "#073966", "#083e6d", "#0a4374", "#0d497d", "#0f4e82", "#125387", "#15588b", "#185d8e",
        "#1b6190", "#1e6591", "#216991", "#246c91", "#266f90", "#28728f", "#2b758e", "#2d778c",
        "#2f798b", "#317c8a", "#347e88", "#368087", "#388285", "#3a8484", "#3d8682", "#3f8981",
        "#428c7f", "#458e7d", "#48917c", "#4b937a", "#4e9678", "#519976", "#559c74", "#58a072",
        "#5ca370", "#60a76e", "#65ab6c", "#6aaf6a", "#70b369", "#76b768", "#7dbc68", "#85c169",
        "#8ec66b", "#98cb6f", "#a2cf74", "#acd47b", "#b5d883", "#c1dc8d", "#c9e096", "#d1e39f",
        "#d8e5a8", "#dfe8b0", "#e5eab8", "#eaedbf", "#efefc6", "#f4f1cd", "#f8f3d3", "#fcf4d9"],
    "glasgow": [
        "#361338", "#3a1435", "#3e1532", "#41162f", "#45172c", "#481829", "#4b1926", "#4f1a23",
        "#521b20", "#561c1d", "#591d1a", "#5e1f16", "#622113", "#67230f", "#6b260b", "#6e2a08",
        "#712e05", "#733303", "#743802", "#743c01", "#754100", "#744500", "#744a00", "#744e01",
        "#745201", "#745603", "#735a06", "#725f0b", "#716311", "#706618", "#6f6a20", "#6e6e27",
        "#6c7231", "#6b7538", "#6a7940", "#687c48", "#677f4f", "#668257", "#65855f", "#638866",
        "#628b6e", "#618e76", "#60927d", "#5f9585", "#60988c", "#619b94", "#649f9b", "#68a2a3",
        "#6ea5aa", "#74a9b0", "#7bacb7", "#82afbc", "#89b2c2", "#92b6c9", "#99b9ce", "#a0bbd3",
        "#a6bed8", "#adc1dd", "#b4c3e2", "#bbc6e7", "#c2c9ed", "#caccf3", "#d2d0f9", "#dbd3ff"],
}


def get_cmap(name: str):
    """Return a Matplotlib colormap; ``<name>_r`` gives the reversed map."""
    reverse = name.endswith("_r")
    base = name[:-2] if reverse else name
    if base not in LUTS:
        return matplotlib.colormaps.get_cmap(name)
    cmap = LinearSegmentedColormap.from_list(base, LUTS[base], N=256)
    return cmap.reversed() if reverse else cmap


def stops(name: str, n: int = 16) -> list[dict]:
    """Evenly spaced ``{fraction, colour}`` stops for browser colour bars."""
    from matplotlib.colors import to_hex
    cmap = get_cmap(name)
    return [{"fraction": round(i / (n - 1), 4), "colour": to_hex(cmap(i / (n - 1)))}
            for i in range(n)]


def register() -> None:
    """Register every map (and its ``_r``) with Matplotlib, so plain
    ``cmap="batlow"`` strings work in any figure script."""
    for base in LUTS:
        for name in (base, f"{base}_r"):
            if name not in matplotlib.colormaps:
                matplotlib.colormaps.register(get_cmap(name), name=name)


register()
