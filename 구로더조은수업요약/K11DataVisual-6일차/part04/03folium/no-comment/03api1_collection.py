# -*- coding: utf-8 -*-
import requests, json

url = 'https://openapi.gg.go.kr/Jnclluniv?'
params = dict(
    Type='json',
    pSize='10',
    KEY='37036b829e80435b9bd513cb9d7cdfd3')
raw_data = requests.get(url=url, params=params)
binary_data = raw_data.content
json_data = json.loads(binary_data)
print(json_data)

for jd in json_data['Jnclluniv'][1]['row']:
    SIGUN_NM = jd['SIGUN_NM']
    FACLT_NM = jd['FACLT_NM']
    REFINE_LOTNO_ADDR = jd['REFINE_LOTNO_ADDR']
    REFINE_WGS84_LAT = jd['REFINE_WGS84_LAT']
    REFINE_WGS84_LOGT = jd['REFINE_WGS84_LOGT']
    print(FACLT_NM, REFINE_WGS84_LAT, REFINE_WGS84_LOGT)

