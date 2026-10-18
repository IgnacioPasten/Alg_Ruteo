"""A3 · Espacios aéreos del AIP."""

import re

from pyproj import Geod
from pypdf import PdfReader
from shapely.geometry import Polygon, mapping


def transformar(path):
    """Parser acotado al catálogo S6 del informe; falla si cambia su estructura."""
    records=[];geod=Geod(ellps='WGS84')
    reader=PdfReader(path)
    for code in ['SC-P29','SC-P30','SC-P50']:
        found=[]
        for page_number,page in enumerate(reader.pages,1):
            text=page.extract_text() or ''
            if code not in text:continue
            block=re.split(r'SC-[PRD]\d+',text.split(code,1)[1])[0]
            coord=re.search(r'(\d{2})\s+(\d{2})\s+(\d{2}(?:[.,]\d+)?)\s*S\s*/?\s*(\d{2})\s+(\d{2})\s+(\d{2}(?:[.,]\d+)?)\s*W',block)
            radius=re.search(r'(?:radio\s+|de\s+)(\d+(?:[.,]\d+)?)\s*(NM|m)\b',block,re.I)
            if not coord or not radius:raise ValueError('AIP cambió; revisar parser '+code)
            a,b,c,d,e,f=map(lambda s:float(s.replace(',','.')),coord.groups())
            lat=-(a+b/60+c/3600);lon=-(d+e/60+f/3600)
            metres=float(radius[1].replace(',','.'))*(1852 if radius[2].upper()=='NM' else 1)
            coords=[geod.fwd(lon,lat,bearing,metres)[:2] for bearing in range(360)];coords.append(coords[0])
            found.append(dict(provider_id=code,code=code,geometry=mapping(Polygon(coords)),
                radius_m=metres,center=[lon,lat],lower_limit='GND/MSL (ver original)',
                upper_limit='Conservado en original_record; exclusión 2D',conditions=block.strip(),
                document_page=str(page_number),original_record=block.strip()))
        if len(found)!=1:raise ValueError('AIP registro ausente/ambiguo '+code)
        records.extend(found)
    return records

if __name__ == '__main__':
    from core.aerial_etl import main  # import local para evitar import circular
    main('A3')
