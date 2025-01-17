# -*- coding: utf-8 -*-
#오라클연결, 특정URL의 정보 얻어오기, JSON파싱을 위한 모듈 임포트
import cx_Oracle as cx
import requests, json

#오라클 사용을 위한 계정정보 설정 및 연결 그리고 커서생성
host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
connect_info = cx.makedsn(host_name, oracle_port, service_name)
conn = cx.connect('study', '1234', connect_info)
cursor = conn.cursor()
 
#경기 공공데이터 OpenAPI에서 대학정보를 요청한다. 
url = 'https://openapi.gg.go.kr/Jnclluniv?'
params = dict(
    Type='json',
    pSize='252',
    KEY='37036b829e80435b9bd513cb9d7cdfd3')
#OpenAPI에서 읽어온 로우데이터를 JSON으로 변환한다. 
raw_data = requests.get(url=url, params=params)
binary_data = raw_data.content
json_data = json.loads(binary_data)
#print(json_data)

#JSON을 파싱한다. 
for jd in json_data['Jnclluniv'][1]['row']:
    SIGUN_NM = jd['SIGUN_NM']
    FACLT_NM = jd['FACLT_NM']
    REFINE_LOTNO_ADDR = jd['REFINE_LOTNO_ADDR']
    REFINE_WGS84_LAT = jd['REFINE_WGS84_LAT']
    REFINE_WGS84_LOGT = jd['REFINE_WGS84_LOGT']
    # print(FACLT_NM, REFINE_WGS84_LAT, REFINE_WGS84_LOGT)
    
    #파싱한 정보는 테이블에 입력한다.                 
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
#자원해제 
conn.close()
