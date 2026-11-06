# CAMS 외부 데이터 (에어로졸·전운량·일사량 예보)

이 폴더에는 **외부 소스 CAMS 자료만** 들어 있습니다. 대회 제공 데이터는 들어 있지 않습니다.

| 경로 | 내용 | 크기 |
|---|---|---|
| `ext_data/cams/raw/cams_run12_<시작>_<끝>.zip` (17개) | ADS에서 받은 원본 그대로 (zip 안에 `data_sfc.nc` 하나) | 약 122MB |
| `ext_data/cams/cams_box.parquet` | 원본을 고정 박스 6개로 요약한 학습용 특징 표 | 약 4.6MB |

## 1. 출처와 이용 조건

- **자료:** Copernicus Atmosphere Monitoring Service (CAMS) global atmospheric composition forecasts
- **주소:** https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts
- **제공처:** Atmosphere Data Store (ADS), ECMWF가 운영
- **라이선스:** Copernicus 제품 라이선스(CC-BY 4.0). 상업적 이용과 가공, 재배포가 허용되고 출처 표기가 필요합니다.
- **출처 표기:** "Contains modified Copernicus Atmosphere Monitoring Service information 2026. Neither the European Commission nor ECMWF is responsible for any use that may be made of the information it contains."
- **받는 조건:** ADS 무료 계정이 필요하고, 데이터셋 페이지에서 라이선스에 동의해야 합니다.

## 2. 받은 방법 (원본 재현)

ADS 다운로드 양식이나 `cdsapi`로 아래 값을 요청했습니다.

```python
{
  "date": ["<시작>/<끝>"],          # 실행일 범위 (파일 이름의 날짜)
  "time": ["12:00"],                # 12 UTC 실행만
  "leadtime_hour": ["27", ..., "51"],
  "type": ["forecast"],
  "data_format": "netcdf_zip",
  "variable": ["total_aerosol_optical_depth_550nm",
               "total_cloud_cover",
               "surface_solar_radiation_downwards"],
  "area": [40, 124, 32, 131]        # 북, 서, 남, 동
}
```

- 요청 한 번의 비용 상한(10,000 = 일수 × 리드 25개 × 변수 3개)과 사용자당 대기 요청 3개 제한이 있어서, 약 4개월씩 17번에 나눠 받았습니다.
- 2024-02-29는 양식에서 거부되어 그 묶음은 2024-02-28에서 끊었습니다.
- 파일 이름의 날짜는 **실행일**입니다. 대상일은 실행일보다 이틀 뒤입니다.

| 파일 | 실행일 | 대상일 |
|---|---|---|
| `cams_run12_20210227_20210629.zip` | 2021-02-27 ~ 06-29 | 2021-03-01 ~ 07-01 |
| … (중간 15개, 이어지는 구간) | | |
| `cams_run12_20260401_20260530.zip` | 2026-04-01 ~ 05-30 | 2026-04-03 ~ 06-01 |

## 3. 예측시점 규칙과 시각 대응

대회 규칙상 대상일 D의 예측은 **전날(D−1) 17:00 KST 이전에 공개된 값**만 쓸 수 있습니다.

| 실행 | 공개 보장 시각 | 사용 여부 |
|---|---|---|
| D−1 00 UTC | 10:00 UTC = D−1 **19:00 KST** | 17시를 넘겨 **사용 안 함** |
| D−2 12 UTC | 22:00 UTC = D−1 **07:00 KST** | **사용** (17시보다 10시간 앞섬) |

따라서 대상일 D의 값은 **D−2 12 UTC 실행의 리드 28~51시간**입니다.

- 리드 28 → 유효시각 D−1 16:00 UTC → `ts` = D 01:00 KST
- 리드 51 → 유효시각 D 15:00 UTC → `ts` = D+1 00:00 KST
- 리드 27은 일사량 누적값의 차분에만 씁니다.

## 4. `cams_box.parquet` 형식

- **인덱스 `ts`:** `datetime64[ns, Asia/Seoul]`. 그 시각에 **끝나는** 1시간입니다(대회 자료와 같은 규칙).
- **기간:** 2021-03-01 01:00 ~ 2026-06-02 00:00 KST, 46,032행.
- **열 18개 (float32):** `cams_{박스}_{변수}`

| 변수 | 원본 이름 | 계산 | 단위 | 범위 |
|---|---|---|---|---|
| `aod` | total_aerosol_optical_depth_550nm | 그 시간 앞뒤 리드 값의 평균 | 없음 | 약 0.01 ~ 2.7 |
| `tcc` | total_cloud_cover | 그 시간 앞뒤 리드 값의 평균 | 0~1 | 0 ~ 1 |
| `ssrd` | surface_solar_radiation_downwards | (리드 L 누적 − 리드 L−1 누적) ÷ 3600 | W/m² | 0 ~ 약 1040 |

**박스 (위도·경도 고정, 발전소 좌표와 무관)** — GFS 박스와 같습니다.

| 박스 | 위도 | 경도 |
|---|---|---|
| `nw` | 37 ~ 39°N | 126 ~ 128°E |
| `ne` | 37 ~ 39°N | 128 ~ 130°E |
| `cw` | 35 ~ 37°N | 126 ~ 128°E |
| `ce` | 35 ~ 37°N | 128 ~ 130°E |
| `sw` | 33 ~ 35°N | 125 ~ 128°E |
| `se` | 33 ~ 35°N | 128 ~ 130°E |

각 박스 안 격자점(0.4°)의 단순 평균입니다. **같은 시각에는 모든 발전소에 18개 열이 똑같이 들어갑니다.** 발전소마다 다른 격자나 가장 가까운 점을 고르지 않습니다.

## 5. 결측

| 구간 | 내용 | 처리 |
|---|---|---|
| 2024-03-02, 03-03 (학습 구간) | 원본에 실행이 없음, 24시간 | 결측으로 둠 |
| 평가 구간 `ssrd` 840여 칸 | 누적값 차분이 음수가 된 칸 (주로 일사가 없는 밤·새벽 시각) | 결측으로 둠 |

결측은 실측이나 다른 자료로 채우지 않습니다.

## 6. 사용 예

```python
import pandas as pd
cams = pd.read_parquet(r"D:\oibc_ext\gfs\cams_box.parquet")      # index ts (KST)
df = df.join(cams, on="ts")                          # 대회 자료 df 의 ts (KST, 시각 끝 기준)와 맞춤
```

## 7. 팀 코드에서 쓰는 법

1. `ext_data/cams/cams_box.parquet`를 GFS 파일들과 같은 `D:\oibc_ext\gfs\`에 복사합니다.
2. 원본부터 다시 만들려면 아래처럼 실행합니다. 결과는 저장소의 `cams_box.parquet`와 값이 완전히 같습니다(차이 0 확인).
   ```
   python v2/cams_box.py build ext_data/cams/raw D:\oibc_ext\gfs\cams_box.parquet
   python v2/cams_box.py check D:\oibc_ext\gfs\cams_box.parquet
   ```
3. ADS에서 직접 다시 받으려면 `pip install cdsapi`, `~/.cdsapirc`에 ADS 키를 넣고 `python v2/cams_box.py fetch 2021-03-01 2026-06-01 ext_data/cams/raw`를 실행합니다.
   받은 zip의 실행일 범위는 `python v2/cams_ident.py ext_data/cams/raw <zip 파일들>`로 확인하고 이름을 맞춥니다.
4. 특징 묶음: `feats.py`에 `GFS4["c"] = [f"cams_{b}_{v}" for b in _BX for v in ("aod","tcc","ssrd")]`를 추가하고 `xehac` 같은 조합 키를 만들면 `lgb_gfs4xehac`, `nn_full_gfs4xc` 등으로 쓸 수 있습니다. 행 표에는 `ts`로 붙입니다.

## 8. 외부 소스 규정 점검

| 규정 | 판단 |
|---|---|
| 자유 공개, 상업적 이용 허용 | 준수 (CC-BY 4.0) |
| 같은 주소에서 누구나 다시 받기 | 준수 (위 주소와 요청값). 무료 계정 필요 |
| 한 번만 공개된 자료 금지 | 준수 (매일 두 번 나오는 정규 운영 예보) |
| 전날 17시 이전 공개 값만 | 준수 (D−2 12 UTC 실행, D−1 07시 KST 공개) |
| 평가 기간 통계로 정규화·그룹 분할 금지 | 준수 (원값 그대로, 정규화 없음) |
| 평가 기간 실측으로 빈 예보 채우기 금지 | 준수 (결측은 그대로) |
| 발전소마다 다른 격자 선택 금지 | 준수 (고정 박스, 전 발전소 같은 값) |
| 출처와 받는 방법 기재 | 이 문서 |
