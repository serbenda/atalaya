"""Sondeo temporal: estructura de las recomendaciones de viaje de Exteriores."""
import re, urllib.request
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; atalaya/1.0)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")
base = "https://www.exteriores.gob.es"
t = get(base + "/es/ServiciosAlCiudadano/Paginas/Recomendaciones-de-viaje.aspx")
print("enlaces a paises:", len(set(re.findall(r'Detalle-recomendaciones-de-viaje\.aspx\?trc=([^"&]+)', t))))
for kw in ["nivel", "Nivel", "riesgo", "desaconseja", "precauci", "color", "data-", "json"]:
    idx = [m.start() for m in re.finditer(kw, t)][:3]
    for i in idx:
        print(f"[{kw}]", re.sub(r"\s+", " ", t[max(0, i - 250):i + 250]))
for pais in ["Sud%c3%a1n", "Francia", "M%c3%a9xico", "Ucrania"]:
    print("=" * 100, pais)
    d = get(base + "/es/ServiciosAlCiudadano/Paginas/Detalle-recomendaciones-de-viaje.aspx?trc=" + pais)
    texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", d, flags=re.S)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    i = texto.find("Recomendaciones")
    print("LEN", len(d))
    for kw in ["desaconseja", "Desaconseja", "precaución", "riesgo", "Última actualización", "ltima actualizaci", "Nivel", "nivel"]:
        for m in list(re.finditer(kw, texto))[:2]:
            print(f"  [{kw}]", texto[max(0, m.start() - 200):m.start() + 300])
    for m in re.findall(r'class="[^"]*(?:nivel|riesgo|alert|semaforo|level)[^"]*"[^>]*>', d)[:10]:
        print("  clase:", m)
    for m in re.findall(r'<img[^>]+(?:nivel|riesgo|mapa|semaforo)[^>]*>', d, flags=re.I)[:5]:
        print("  img:", m)
