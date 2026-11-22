import sys, numpy as np
from netCDF4 import Dataset
a, b = Dataset(sys.argv[1]), Dataset(sys.argv[2])
diff = []
for v in a.variables:
    x, y = a[v][:], b[v][:]
    if x.dtype.kind in "SUO" or x.dtype.kind == "S":
        if not np.array_equal(np.asarray(x), np.asarray(y)): diff.append((v, "str"))
        continue
    x, y = np.asarray(x), np.asarray(y)
    if not np.array_equal(x, y, equal_nan=True):
        diff.append((v, float(np.nanmax(np.abs(x.astype(float) - y.astype(float))))))
ga = {k: a.getncattr(k) for k in a.ncattrs()}; gb = {k: b.getncattr(k) for k in b.ncattrs()}
print("vars", len(a.variables), "differing", len(diff), diff[:10])
print("global attrs differing:", [k for k in set(ga) | set(gb) if str(ga.get(k)) != str(gb.get(k))])
