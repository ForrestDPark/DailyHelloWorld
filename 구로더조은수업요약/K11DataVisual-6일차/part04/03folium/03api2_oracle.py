# -*- coding: utf-8 -*-
#오라클 연결을 위한 모듈 임포트
import cx_Oracle as cx
'''
테이블 생성하기 
create table g_univ(	
	idx number primary key, 
	sigun varchar2(20) not null, 
	faclt varchar2(100) not null, 
	addr varchar2(200) not null, 
	latitude number(20,10) not null, 
	longitude number(20,10) not null
); 

시퀀스 생성하기 
create sequence myboard_seq
    start with 1
    increment by 1
    minvalue 1
    nomaxvalue
    nocycle
    nocache;
'''

#오라클 접속을 위한 정보를 변수로 정의한다. 
host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
#오라클 연결을 위한 커넥션 객체 생성
connect_info = cx.makedsn(host_name, oracle_port, service_name)
conn = cx.connect('study', '1234', connect_info)
#쿼리문 실행을 위해 커서를 생성한다. 
cursor = conn.cursor()
      
#더미데이터는 하드코딩으로 준비한 후 입력 테스트를 진행한다. 
SIGUN_NM = "종로구"
FACLT_NM = "더이쁜대학교"
REFINE_LOTNO_ADDR = "서울시 종로구 삼청동"
REFINE_WGS84_LAT = 37.2345
REFINE_WGS84_LOGT = 126.2345

#파이썬에서 인파라미터는 ':변수명' 과 같이 기술한다. 
sql = """insert into g_univ (idx, sigun, faclt, addr, latitude, longitude)
        values (MYBOARD_SEQ.nextval, :sigun, :faclt, :addr, :latitude, :longitude)"""
try: 
    #insert 쿼리문을 실행한다. 이때 인파라미터의 값을 설정한다.
    cursor.execute(sql, sigun=SIGUN_NM, faclt=FACLT_NM, addr=REFINE_LOTNO_ADDR, 
                   latitude=REFINE_WGS84_LAT, longitude=REFINE_WGS84_LOGT)
    #실행에 문제가 없다면 커밋한다. 
    conn.commit()
    print("1개의 레코드 입력")
except Exception as e:    
    #예외가 발생했다면 롤백한다. 
    conn.rollback()
    print("insert 실행시 오류발생", e)
#자원 해제
conn.close()

