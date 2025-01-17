# -*- coding: utf-8 -*-
import requests, json
'''
구글검색 : 전국 대학 위치 데이터 or 경기도 공공 데이터
https://data.gg.go.kr/

데이터셋 - 전문 및 대학교 현황
https://data.gg.go.kr/portal/data/service/selectServicePage.do?page=1&rows=10&sortColumn=&sortDirection=&infId=V8VGMZPEPZH4XN27NXS021454377&infSeq=3&order=&loc=&searchWord=%EC%A0%84%EB%AC%B8+%EB%B0%8F+%EB%8C%80%ED%95%99%EA%B5%90

오픈API 인증키 발급하여 아래 소스코드를 작성한다. 
'''
#OpenAPI 요청 URL 생성
url = 'https://openapi.gg.go.kr/Jnclluniv?'
#파라미터는 딕셔너리로 정의한다. (콜백데이터는 json으로 설정)
params = dict(
    Type='json',
    pSize='10',
    KEY='37036b829e80435b9bd513cb9d7cdfd3')
#준비된 URL과 파라미터를 인수로 해당 페이지 정보를 JSON으로 읽어온다. 
raw_data = requests.get(url=url, params=params)
binary_data = raw_data.content
#로우(Raw)데이터를 JSON데이터로 변환한다. 
json_data = json.loads(binary_data)
#변환된 데이터를 콘솔에서 확인한다. 
print(json_data)
'''
JSON데이터를 분석한 후 키(key)를 찾았다면 아래와 같이 반복문을 통해
필요한 값을 파싱한다. 
'''
for jd in json_data['Jnclluniv'][1]['row']:
    SIGUN_NM = jd['SIGUN_NM'] #시군
    FACLT_NM = jd['FACLT_NM'] #대학명
    REFINE_LOTNO_ADDR = jd['REFINE_LOTNO_ADDR'] #주소
    REFINE_WGS84_LAT = jd['REFINE_WGS84_LAT'] #위도
    REFINE_WGS84_LOGT = jd['REFINE_WGS84_LOGT'] #경도
    print(FACLT_NM, REFINE_WGS84_LAT, REFINE_WGS84_LOGT)

