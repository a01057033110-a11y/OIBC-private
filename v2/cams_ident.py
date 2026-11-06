import sys, zipfile, os, tempfile, shutil, xarray as xr, pandas as pd
D = sys.argv[1]
for f in sys.argv[2:]:
    try:
        z = zipfile.ZipFile(f); n = [x for x in z.namelist() if x.endswith('.nc')]
        t = tempfile.mkdtemp(); z.extractall(t, n)
        ds = xr.open_dataset(os.path.join(t, n[0]))
        ref = next(c for c in ("forecast_reference_time", "time") if c in ds.coords or c in ds.dims)
        r = pd.DatetimeIndex(ds[ref].values); s, e = r.min(), r.max(); ds.close()
        out = f"{D}/cams_run12_{s:%Y%m%d}_{e:%Y%m%d}.zip"
        if not os.path.exists(out): shutil.copy(f, out)
        print(os.path.basename(f), '->', os.path.basename(out), len(r))
    except Exception as ex:
        print(os.path.basename(f), 'ERR', ex)
