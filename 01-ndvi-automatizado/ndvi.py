# ------------------------------------------------------------
# NDVI AUTOMÁTICO POR IMÓVEL
# ------------------------------------------------------------
# ============================================================
# Objetivo: Gerar mapas NDVI por cod_imovel
# Saída: PNG direto (com legenda)
# Execução:
# cd "C:\Users\Eng ASPIPP\OneDrive - aspipp\NDVI\pipeline-central\01-ndvi-automatizado>"
# python ndvi.py -d 2026-05-01
# Dados --- python ndvi.py -d 2026-02-17 -c SP-3535804-4268FFBED5C1491D82C7447A94BE7EAF 
# ============================================================

import ee
import geopandas as gpd
import yaml
from pathlib import Path
from datetime import datetime
import argparse
import sys
from tqdm import tqdm
import requests
from PIL import Image
import matplotlib.pyplot as plt

# ------------------------------------------------------------
# 1. Argumentos
# ------------------------------------------------------------

parser = argparse.ArgumentParser(
    description="Gerar NDVI por imóvel"
)

parser.add_argument(
    "-d",
    "--date",
    required=False,
    help="Data de referência (YYYY-MM-DD)"
)

parser.add_argument(
    "-c",
    "--cod",
    required=False,
    help="Código do imóvel (cod_imovel)"
)

args = parser.parse_args()

ref_date = args.date
cod_filtro = args.cod

# ------------------------------------------------------------
# 2. Entrada interativa
# ------------------------------------------------------------

if not ref_date:
    ref_date = input(
        "📆 Escolha a data (YYYY-MM-DD): "
    ).strip()

if not cod_filtro:
    cod_filtro = input(
        "🏡 Digite o código do imóvel: "
    ).strip()

try:
    datetime.strptime(ref_date, "%Y-%m-%d")
except ValueError:
    sys.exit(
        "❌ Data inválida. Utilize YYYY-MM-DD"
    )

# ------------------------------------------------------------
# 3. Earth Engine
# ------------------------------------------------------------

try:
    ee.Initialize(project="pipeline-central")
except Exception:
    ee.Authenticate()
    ee.Initialize(project="pipeline-central")

# ------------------------------------------------------------
# 4. Configuração
# ------------------------------------------------------------

script_dir = Path(__file__).resolve().parent

# raiz: pipeline-central
project_root = script_dir

# config está dentro de 01-ndvi-automatizado
config_path = script_dir / "config.yaml"

if not config_path.exists():
    sys.exit(
        f"❌ config.yaml não encontrado: {config_path}"
    )

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# pasta compartilhada na raiz
data_dir = project_root / config["paths"]["data_dir"]

# pasta compartilhada de saída
output_dir = project_root / config["paths"]["output_dir"]

output_dir.mkdir(
    parents=True,
    exist_ok=True
)

imoveis_gpkg = (
    data_dir /
    config["dataset"]["ndvi"]["file"]
)

id_field = (
    config["dataset"]["ndvi"]["id_field"]
)

if not imoveis_gpkg.exists():
    sys.exit(
        f"❌ Arquivo não encontrado: {imoveis_gpkg}"
    )

print(f"✅ Config: {config_path}")
print(f"✅ Dados: {data_dir}")
print(f"✅ GPKG: {imoveis_gpkg}")
print(f"✅ Saída: {output_dir}")

# ------------------------------------------------------------
# 5. Ler GPKG
# ------------------------------------------------------------

gdf = gpd.read_file(imoveis_gpkg)

if gdf.empty:
    sys.exit("❌ GeoPackage vazio.")

if id_field not in gdf.columns:
    sys.exit(
        f"❌ Campo '{id_field}' não encontrado."
    )

print(f"\n📦 {len(gdf)} imóveis carregados")

# ------------------------------------------------------------
# 6. Filtrar imóvel
# ------------------------------------------------------------

gdf = gdf[
    gdf[id_field].astype(str)
    == str(cod_filtro)
]

if gdf.empty:
    sys.exit(
        f"❌ cod_imovel '{cod_filtro}' não encontrado."
    )

print(f"🔎 Imóvel selecionado: {cod_filtro}")
print(f"📆 Data NDVI: {ref_date}")

# ------------------------------------------------------------
# 7. Janela temporal
# ------------------------------------------------------------

start_date = ee.Date(ref_date)
end_date = ee.Date(ref_date).advance(1, "day")

# ------------------------------------------------------------
# 8. Funções Earth Engine
# ------------------------------------------------------------

def mask_s2_clouds(img):

    qa = img.select("QA60")

    cloud = qa.bitwiseAnd(
        1 << 10
    ).eq(0)

    cirrus = qa.bitwiseAnd(
        1 << 11
    ).eq(0)

    scl = img.select("SCL")

    shadow = scl.neq(3)

    mask_scl = (
        scl.neq(8)
        .And(scl.neq(9))
    )

    mask = (
        cloud
        .And(cirrus)
        .And(shadow)
        .And(mask_scl)
    )

    return img.updateMask(mask)


def calcula_ndvi(collection):

    ndvi_collection = (
        collection
        .map(mask_s2_clouds)
        .map(
            lambda img: img.addBands(
                img.normalizedDifference(
                    ["B8", "B4"]
                ).rename("NDVI")
            )
        )
    )

    return (
        ndvi_collection
        .qualityMosaic("NDVI")
        .select("NDVI")
    )

# ------------------------------------------------------------
# 9. Legenda
# ------------------------------------------------------------

def adicionar_legenda_ndvi(
        png_path,
        titulo,
        cloud_txt
):

    img = Image.open(png_path)

    fig, ax = plt.subplots(
        figsize=(8, 8)
    )

    ax.imshow(img)
    ax.axis("off")

    cmap = plt.get_cmap("RdYlGn")

    norm = plt.Normalize(
        vmin=0.2,
        vmax=0.8
    )

    cbar = plt.colorbar(
        plt.cm.ScalarMappable(
            norm=norm,
            cmap=cmap
        ),
        ax=ax,
        fraction=0.035,
        pad=0.04
    )

    cbar.set_label(
        "NDVI",
        fontsize=9
    )

    cbar.ax.tick_params(
        labelsize=8
    )

    ax.set_title(
        titulo,
        fontsize=11,
        pad=10
    )

    ax.text(
        0.02,
        0.02,
        cloud_txt,
        transform=ax.transAxes,
        fontsize=9,
        color="black",
        bbox=dict(
            facecolor="white",
            alpha=0.7,
            edgecolor="none"
        )
    )

    plt.savefig(
        png_path,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close()

# ------------------------------------------------------------
# 10. Processamento
# ------------------------------------------------------------

print("\n🌱 Gerando NDVI...\n")

for row in tqdm(
    gdf.itertuples(),
    total=len(gdf)
):

    cod = getattr(row, id_field)

    geom = row.geometry

    geom_ee = ee.Geometry(
        geom.__geo_interface__
    )

    collection = (
        ee.ImageCollection(
            config["sentinel2"]["collection"]
        )
        .filterBounds(geom_ee)
        .filterDate(
            start_date,
            end_date
        )
    )

    n_img = collection.size().getInfo()

    if n_img == 0:

        print(
            f"⚠️ {cod} → sem imagens"
        )

        continue

    cloud = (
        collection
        .aggregate_min(
            "CLOUDY_PIXEL_PERCENTAGE"
        )
        .getInfo()
    )

    cloud_txt = (
        f"Nuvens (data): {cloud:.1f}%"
    )

    ndvi = (
        calcula_ndvi(collection)
        .clip(geom_ee)
    )

    ndvi_vis = ndvi.visualize(
        min=0.0,
        max=0.8,
        palette=[
            "#d7191c",
            "#f07c4a",
            "#fdae61",
            "#fee08b",
            "#d9ef8b",
            "#a6d96a",
            "#66bd63",
            "#1a9641"
        ]
    )

    url = ndvi_vis.getThumbURL({
        "region": geom_ee,
        "scale": 10,
        "format": "png"
    })

    temp_png = script_dir / "ndvi_temp.png"

    try:

        response = requests.get(
            url,
            timeout=120
        )

        response.raise_for_status()

        with open(
            temp_png,
            "wb"
        ) as f:

            f.write(
                response.content
            )

    except Exception as e:

        print(
            f"❌ erro download {cod}: {e}"
        )

        continue

    titulo = (
        f"NDVI - {cod} - {ref_date}"
    )

    adicionar_legenda_ndvi(
        temp_png,
        titulo,
        cloud_txt
    )

    print(
        f"✅ Imagem temporária criada: {temp_png}"
    )

print("\n✅ Finalizado\n")