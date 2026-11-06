"""CAMS 전지구 예보(에어로졸·일사량·전운량)를 받아서 고정 박스 6개로 요약한다.

출처   Copernicus Atmosphere Monitoring Service (CAMS) global atmospheric composition forecasts
       Atmosphere Data Store(ADS) API, 데이터셋 이름: cams-global-atmospheric-composition-forecasts
       https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts
이용   ADS 계정과 API 키가 필요하고, 데이터셋 페이지에서 라이선스(CC-BY)에 동의해야 한다. 출처 표기 필수.
받기   cdsapi 로 월 단위 요청 (재실행하면 받아 둔 달은 건너뛴다)

■ 어떤 실행을 쓰나 (전날 17시 규칙)
  CAMS 00 UTC 실행은 10:00 UTC(한국 19시)에야 공개가 보장되어 17시 시한을 넘는다.
  12 UTC 실행은 22:00 UTC(한국 다음날 07시)까지 공개가 보장된다.
  그래서 대상일 D 의 값은 "D-2 일의 12 UTC 실행"의 리드 28~51시간을 쓴다.
    ts = D 01:00 KST  → 유효시각 (D-1) 16:00 UTC → 리드 28
    ts = D+1 00:00 KST → 유효시각 D 15:00 UTC → 리드 51
  (GFS 는 15~39시간이라 CAMS 쪽이 정보가 12시간쯤 더 오래됐다. 효과가 작을 수 있다.)

■ 변수 (모두 지표 변수, 1시간 간격)
  aod550  total_aerosol_optical_depth_550nm  (순간값, 2018-06-26 12UTC부터 존재)
  tcc     total_cloud_cover                  (순간값, 0~1)
  ssrd    surface_solar_radiation_downwards  (J/m², 예보 시작부터의 누적 → 이웃 리드의 차이 ÷ 3600 = W/m²)

■ 박스 (GFS 와 같은 고정 영역, 모든 발전소에 같은 값)
  nw 37~39N 126~128E / ne 37~39N 128~130E / cw 35~37N 126~128E
  ce 35~37N 128~130E / sw 33~35N 125~128E / se 33~35N 128~130E

사용법
  pip install cdsapi xarray netCDF4 pandas pyarrow numpy
  ~/.cdsapirc 에  url: https://ads.atmosphere.copernicus.eu/api  /  key: <내 키>
  python cams_box.py fetch 2021-01-01 2026-05-31 raw_cams      # 받기 (대상일 기준 기간)
  python cams_box.py build raw_cams cams_box.parquet            # 박스 요약 → parquet
  python cams_box.py check cams_box.parquet                     # 점검 출력
  python cams_box.py selftest                                   # 가짜 데이터로 계산 점검 (인터넷 불필요)

결과 parquet: 인덱스 ts (Asia/Seoul, 시각 끝 기준), 열 cams_{박스}_{aod|tcc|ssrd} (float32).
팀 코드에서는 gfs_box.parquet 와 같은 방식으로 d.join(pd.read_parquet(...), on="ts") 하면 된다.
"""
import os
import sys
import zipfile
import glob
import numpy as np
import pandas as pd

DATASET = "cams-global-atmospheric-composition-forecasts"
VARS_API = ["total_aerosol_optical_depth_550nm", "total_cloud_cover", "surface_solar_radiation_downwards"]
AREA = [40, 124, 32, 131]                      # 북, 서, 남, 동 (박스를 모두 덮는 영역)
LEADS = [str(h) for h in range(27, 52)]        # 27 은 ssrd 차분용, 28~51 이 대상일
BOXES = {"nw": ((37, 39), (126, 128)), "ne": ((37, 39), (128, 130)),
         "cw": ((35, 37), (126, 128)), "ce": ((35, 37), (128, 130)),
         "sw": ((33, 35), (125, 128)), "se": ((33, 35), (128, 130))}
SHORT = {"aod550": "aod", "tcc": "tcc", "ssrd": "ssrd"}
KST = "Asia/Seoul"


def months(first_day, last_day):
    """대상일 범위 → (실행일 범위) 월 단위 목록. 대상일 D 의 실행일은 D-2."""
    a = pd.Timestamp(first_day) - pd.Timedelta(days=2)
    b = pd.Timestamp(last_day) - pd.Timedelta(days=2)
    cur = a.replace(day=1)
    while cur <= b:
        end = min((cur + pd.offsets.MonthEnd(0)), b)
        yield max(cur, a), end
        cur = cur + pd.offsets.MonthBegin(1)


def fetch(first_day, last_day, outdir):
    import cdsapi
    os.makedirs(outdir, exist_ok=True)
    c = cdsapi.Client()
    for s, e in months(first_day, last_day):
        path = os.path.join(outdir, f"cams_run12_{s:%Y%m%d}_{e:%Y%m%d}.zip")
        if os.path.exists(path):
            continue
        req = {
            "variable": VARS_API,
            "date": [f"{s:%Y-%m-%d}/{e:%Y-%m-%d}"],
            "time": ["12:00"],
            "leadtime_hour": LEADS,
            "type": ["forecast"],
            "area": AREA,
            "data_format": "netcdf_zip",       # 문자열 값만 쓴다 (ADS 요구)
        }
        print("요청", s.date(), "~", e.date(), flush=True)
        c.retrieve(DATASET, req, path + ".part")
        os.replace(path + ".part", path)


def _open(zpath, tmp):
    import xarray as xr
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n.endswith(".nc")]
        z.extractall(tmp, names)
    dss = [xr.open_dataset(os.path.join(tmp, n)) for n in names]
    return xr.merge(dss, compat="override") if len(dss) > 1 else dss[0]


def _coords(ds):
    """참조(실행) 시각, 리드 시간, 위경도 좌표 이름을 찾는다."""
    ref = next(n for n in ("forecast_reference_time", "time") if n in ds.coords or n in ds.dims)
    lead = next(n for n in ("forecast_period", "step", "leadtime_hour") if n in ds.coords or n in ds.dims)
    lat = next(n for n in ("latitude", "lat") if n in ds.coords)
    lon = next(n for n in ("longitude", "lon") if n in ds.coords)
    return ref, lead, lat, lon


def box_series(ds):
    """ds → DataFrame(index=ts KST, columns=cams_{box}_{var}). 변수별 처리는 모듈 설명 참고."""
    ref, lead, lat, lon = _coords(ds)
    L = ds[lead]
    if np.issubdtype(L.dtype, np.timedelta64):
        lead_h = (L / np.timedelta64(1, "h")).astype(float).values
    else:
        lead_h = L.values.astype(float)
    refs = pd.DatetimeIndex(ds[ref].values)
    la, lo = ds[lat].values, ds[lon].values
    out = {}
    for var in ("aod550", "tcc", "ssrd"):
        if var not in ds:
            continue
        da = ds[var].transpose(ref, lead, lat, lon).values.astype("float64")      # (실행, 리드, 위도, 경도)
        for b, ((y0, y1), (x0, x1)) in BOXES.items():
            my = (la >= y0) & (la <= y1)
            mx = (lo >= x0) & (lo <= x1)
            v = np.nanmean(da[:, :, my][:, :, :, mx], axis=(2, 3))                  # (실행, 리드)
            out[(var, b)] = v
    # 실행(run)마다 따로 계산한다: 이웃 리드의 차분·평균은 같은 실행 안에서만 만든다.
    # 리드 27 은 차분용 보조 행이라 결과에서 뺀다 (남는 것은 리드 28~51 = 대상일 D 의 24시각).
    frames = []
    for i, r in enumerate(refs):
        cols = {}
        for b in BOXES:
            if ("ssrd", b) in out:
                acc = out[("ssrd", b)][i]
                flux = np.full_like(acc, np.nan)
                flux[1:] = (acc[1:] - acc[:-1]) / 3600.0                              # W/m², 직전 한 시간 평균
                flux[flux < -1e-6] = np.nan                                           # 누적이 되감긴 칸은 결측
                cols[f"cams_{b}_ssrd"] = np.clip(flux, 0, None)
            for var in ("aod550", "tcc"):
                if (var, b) in out:
                    v = out[(var, b)][i]
                    mid = np.full_like(v, np.nan)
                    mid[1:] = (v[1:] + v[:-1]) / 2                                    # 시각 구간의 가운데 값
                    cols[f"cams_{b}_{SHORT[var]}"] = mid
        f = pd.DataFrame(cols)
        valid_utc = r + pd.to_timedelta(lead_h, unit="h")
        f.index = pd.DatetimeIndex(valid_utc + pd.Timedelta(hours=9))                 # ts = 한국 시각, 구간 끝 기준
        frames.append(f[lead_h > lead_h.min()])
    res = pd.concat(frames).sort_index()
    return res[~res.index.duplicated(keep="last")]


def build(rawdir, outpath):
    import tempfile
    parts = []
    for z in sorted(glob.glob(os.path.join(rawdir, "cams_run12_*.zip"))):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _open(z, tmp)
            parts.append(box_series(ds))
            ds.close()
        print("처리", os.path.basename(z), flush=True)
    d = pd.concat(parts).sort_index()
    d = d[~d.index.duplicated(keep="last")]
    # 대상일 규칙: ts 는 (D 01:00 ~ D+1 00:00) 만 남긴다. 리드 27 의 차분용 행은 이웃 실행의 값과 섞이지 않게 제거.
    keep = d.dropna(how="all").index
    d = d.loc[keep]
    d.index = d.index.tz_localize(KST)
    d.astype("float32").to_parquet(outpath)
    print("저장", outpath, d.shape)


def check(path):
    d = pd.read_parquet(path)
    print("행", len(d), "기간", d.index.min(), "~", d.index.max())
    print("결측률 상위\n", d.isna().mean().sort_values(ascending=False).head(5).round(4))
    noon = d[d.index.hour == 13]
    for c in [c for c in d.columns if c.endswith("ssrd")][:3]:
        print(c, "13시 평균 %.0f W/m², 최대 %.0f" % (noon[c].mean(), d[c].max()))
    print("ssrd 음수 개수", int((d.filter(like="ssrd") < 0).sum().sum()), " tcc 범위", float(d.filter(like="tcc").min().min()), float(d.filter(like="tcc").max().max()))


def selftest():
    """가짜 데이터: ssrd 누적이 매시 100 W/m² 로 늘면 차분이 100 이 되는지, 시각 대응이 맞는지 본다."""
    import xarray as xr
    runs = pd.to_datetime(["2022-03-01 12:00", "2022-03-02 12:00"])   # D-2 의 12 UTC → 대상일 D = 03-03, 03-04
    leads = np.arange(27, 52)
    lat = np.arange(40, 31.9, -0.4)
    lon = np.arange(124, 131.1, 0.4)
    shp = (len(runs), len(leads), len(lat), len(lon))
    ssrd = np.broadcast_to((leads * 3600.0 * 100)[None, :, None, None], shp).copy()
    ssrd[1] += 5e6                                                   # 둘째 실행은 누적 기준이 다름: 이웃 실행과 섞이면 값이 튄다
    tcc = np.full(shp, 0.5)
    aod = np.full(shp, 0.2)
    ds = xr.Dataset({"ssrd": (("forecast_reference_time", "forecast_period", "latitude", "longitude"), ssrd),
                     "tcc": (("forecast_reference_time", "forecast_period", "latitude", "longitude"), tcc),
                     "aod550": (("forecast_reference_time", "forecast_period", "latitude", "longitude"), aod)},
                    coords={"forecast_reference_time": runs, "forecast_period": leads, "latitude": lat, "longitude": lon})
    r = box_series(ds)
    x = r["cams_nw_ssrd"].dropna()
    assert len(x) == 48 and np.allclose(x.values, 100), (len(x), x.describe())     # 실행 경계에서도 항상 100
    assert abs(r["cams_se_tcc"].dropna().iloc[3] - 0.5) < 1e-9
    ts = r.dropna(how="all").index
    d0 = pd.Timestamp("2022-03-03 01:00")                              # ts D 01:00 KST 이 리드 28 에 해당해야 한다
    assert d0 in ts, "리드 28 의 시각 대응이 틀림"
    assert pd.Timestamp("2022-03-05 00:00") in ts and not ts.duplicated().any(), "리드 51 의 시각 대응이 틀림"
    print("selftest 통과: 차분 100 W/m², ts 범위", ts.min(), "~", ts.max())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "fetch":
        fetch(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "build":
        build(sys.argv[2], sys.argv[3])
    elif cmd == "check":
        check(sys.argv[2])
    else:
        selftest()
