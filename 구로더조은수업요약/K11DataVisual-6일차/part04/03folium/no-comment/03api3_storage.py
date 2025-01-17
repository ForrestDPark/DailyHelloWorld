# -*- coding: utf-8 -*-
import cx_Oracle as cx
import requests, json

host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
connect_info = cx.makedsn(host_name, oracle_port, service_name)
conn = cx.connect('kosmo', '1234', connect_info)
cursor = conn.cursor()
 
url = 'https://openapi.gg.go.kr/Jnclluniv?'
params = dict(
    Type='json',
    pSize='252',
    KEY='37036b829e80435b9bd513cb9d7cdfd3')
raw_data = requests.get(url=url, params=params)
binary_data = raw_data.content
json_data = json.loads(binary_data)
#print(json_data)

for jd in json_data['Jnclluniv'][1]['row']:
    SIGUN_NM = jd['SIGUN_NM']
    FACLT_NM = jd['FACLT_NM']
    REFINE_LOTNO_ADDR = jd['REFINE_LOTNO_ADDR']
    REFINE_WGS84_LAT = jd['REFINE_WGS84_LAT']
    REFINE_WGS84_LOGT = jd['REFINE_WGS84_LOGT']
    # print(FACLT_NM, REFINE_WGS84_LAT, REFINE_WGS84_LOGT)
                
    sql = """insert into g_univ (idx, sigun, faclt, addr, latitude, longitude)
           values (MYBOARD_SEQ.nextval, :sigun, :faclt, :addr, :latitude, :longitude)"""
           
    try:
       cursor.execute(sql, sigun=SIGUN_NM, faclt=FACLT_NM, addr=REFINE_LOTNO_ADDR, 
                      latitude=REFINE_WGS84_LAT, longitude=REFINE_WGS84_LOGT)
       conn.commit()
       print("1개의 레코드 입력")
    except Exception as e:
        conn.rollback()
        print("insert 실행시 오류발생", e)
 
conn.close()

