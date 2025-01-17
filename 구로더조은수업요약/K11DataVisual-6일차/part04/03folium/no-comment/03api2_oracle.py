# -*- coding: utf-8 -*-
import cx_Oracle as cx
host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
connect_info = cx.makedsn(host_name, oracle_port, service_name)
conn = cx.connect('kosmo', '1234', connect_info)
cursor = conn.cursor()
      
SIGUN_NM = "나의시군1"
FACLT_NM = "코스모대학교1"
REFINE_LOTNO_ADDR = "서울시1 금천구 가산동 월드메르디앙"
REFINE_WGS84_LAT = 37.1234
REFINE_WGS84_LOGT = 126.1234

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

