# ------------------------------------------------------------
# VERIFICAÇÃO DE IMAGENS DISPONÍVEIS
# ------------------------------------------------------------
# ============================================================
# cd "C:\Users\Eng ASPIPP\OneDrive - aspipp\NDVI\pipeline-central\01-ndvi-automatizado"
# Script: python verificar_imagens.py
# Objetivo: Verificar datas Sentinel-2 e nível de nuvem
# Imovel: SP-3535804-4268FFBED5C1491D82C7447A94BE7EAF
# ============================================================

# pyright: reportPrivateImportUsage=false
# ============================================================

import ee
import geopandas as gpd
import yaml
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import sys

# ------------------------------------------------------------
# 1. Autenticação Earth Engine
# ------------------------------------------------------------

try:
    ee.Initialize(project="pipeline-central")
except Exception:
    ee.Authenticate()
    ee.Initialize(project="pipeline-central")

# ------------------------------------------------------------
# 2. Caminhos e config.yaml
# ------------------------------------------------------------
# ------------------------------------------------------------
# 2. Caminhos e config.yaml
# ------------------------------------------------------------

script_dir = Path(__file__).resolve().parent

# raiz do projeto (pipeline-central)
project_root = script_dir.parent

# config.yaml fica junto do script
config_path = script_dir / "config.yaml"

if not config_path.exists():
    sys.exit(f"❌ config.yaml não encontrado: {config_path}")

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# pasta data compartilhada na raiz do projeto
data_dir = project_root / config["paths"]["data_dir"]

region_gpkg = data_dir / config["dataset"]["verificacao"]["file"]

if not region_gpkg.exists():
    sys.exit(f"❌ Arquivo não encontrado: {region_gpkg}")

print(f"✅ Config carregado: {config_path}")
print(f"✅ Pasta de dados: {data_dir}")
print(f"✅ GeoPackage: {region_gpkg}")

# ------------------------------------------------------------
# 3. Parâmetros
# ------------------------------------------------------------

days_back = config["temporal"]["days_back"]

end_date = datetime.today()
start_date = end_date - timedelta(days=days_back)

collection_id = config["sentinel2"]["collection"]
cloud_limit = config["sentinel2"]["cloud_coverage_max"]

# ------------------------------------------------------------
# 4. Ler GPKG
# ------------------------------------------------------------

gdf = gpd.read_file(region_gpkg)

if gdf.empty:
    sys.exit("❌ GeoPackage vazio.")

print(f"\n✅ Total de geometrias: {len(gdf)}")

# ------------------------------------------------------------
# 5. Escolha do modo
# ------------------------------------------------------------

print("\nComo deseja verificar as imagens?\n")
print("1 - Região inteira")
print("2 - Um imóvel específico\n")

opc = input("Escolha (1 ou 2): ").strip()

if opc == "2":

    cod_imovel = input(
        "\nDigite o cod_imovel: "
    ).strip()

    gdf_sel = gdf[
        gdf["cod_imovel"].astype(str) == cod_imovel
    ]

    if gdf_sel.empty:
        sys.exit(
            f"❌ cod_imovel não encontrado: {cod_imovel}"
        )

    geom = gdf_sel.geometry.iloc[0]

    region_ee = ee.Geometry(
        geom.__geo_interface__
    )

    print(
        f"\n✅ Imóvel selecionado: {cod_imovel}"
    )

else:

    bounds = gdf.total_bounds

    region_ee = ee.Geometry.Rectangle([
        bounds[0],
        bounds[1],
        bounds[2],
        bounds[3]
    ])

    print("\n✅ Modo região (bounding box)")

# ------------------------------------------------------------
# 6. Sentinel-2
# ------------------------------------------------------------

collection = (
    ee.ImageCollection(collection_id)
    .filterBounds(region_ee)
    .filterDate(
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d")
    )
    .filter(
        ee.Filter.lt(
            "CLOUDY_PIXEL_PERCENTAGE",
            cloud_limit
        )
    )
)

total = collection.size().getInfo()

if total == 0:
    print("\n❌ Nenhuma imagem disponível.")
    sys.exit(0)

print(
    f"\n🛰️ Total de imagens encontradas: {total}"
)

# ------------------------------------------------------------
# 7. Extrair informações
# ------------------------------------------------------------

def extract_info(img):
    return ee.Feature(
        None,
        {
            "date": ee.Date(
                img.get("system:time_start")
            ).format("YYYY-MM-dd"),
            "cloud": img.get(
                "CLOUDY_PIXEL_PERCENTAGE"
            )
        }
    )

fc = collection.map(extract_info)

features = fc.getInfo()["features"]

# ------------------------------------------------------------
# 8. Agrupar por data
# ------------------------------------------------------------

by_date = defaultdict(list)

for feat in features:

    props = feat["properties"]

    date = props["date"]
    cloud = props["cloud"]

    if cloud is not None:
        by_date[date].append(cloud)

results = []

for date, clouds in by_date.items():

    results.append({
        "date": date,
        "cloud": sum(clouds) / len(clouds),
        "scenes": len(clouds)
    })

results.sort(
    key=lambda x: (
        x["cloud"],
        x["date"]
    )
)

# ------------------------------------------------------------
# 9. Saída
# ------------------------------------------------------------

print("\n📅 Imagens Sentinel-2 disponíveis:\n")
print(f"{'Data':<12} {'Nuvem (%)':<12} {'Imagens'}")
print("-" * 36)

for r in results:

    print(
        f"{r['date']:<12} "
        f"{r['cloud']:<12.2f} "
        f"{r['scenes']}"
    )

best = results[0]

print("\n👉 Melhor data:")
print(f"📆 {best['date']}")
print(f"☁️ {best['cloud']:.2f}%")
print(f"🛰️ {best['scenes']} cenas")