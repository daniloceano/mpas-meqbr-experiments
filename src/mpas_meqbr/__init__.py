"""Analysis package for the MeqBr ~5 km MPAS experiment set.

Layout of responsibilities — nothing else in the repo should duplicate these:

``config``   resolve machine paths + experiment/site metadata, in one place
``io``       list and open MPAS history files without loading whole 3D fields
``mesh``     cell lookup (nearest ocean cell), regridding, native-mesh plotting
``vertical`` layer-center heights and height-to-level matching
``obs``      LiDAR and ISD station readers, QC, hourly aggregation
``era5``     ERA5 readers for the simulation periods and the 1990-2020 archive
``metrics``  verification statistics, wind-resource statistics, block bootstrap
``plotting`` shared figure style and map helpers
"""

__version__ = "0.1.0"

__all__ = [
    "config", "io", "mesh", "vertical", "obs", "era5", "metrics", "plotting",
]
