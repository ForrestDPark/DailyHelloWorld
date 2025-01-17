# -*- coding: utf-8 -*-
#오라클 사용을 위해 cx_oracle 모듈을 설치한 후 임포트한다. 
import cx_Oracle as cx

#오라클 접속정보 및 계정정보를 선언한다. 
host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
connect_info = cx.makedsn(host_name, oracle_port, service_name)
#오라클 접속
conn = cx.connect('musthave', '1234', connect_info)
#쿼리실행을 위해 cursor객체를 생성한다. 
cursor = conn.cursor()

#인파라미터가 없는 정적쿼리문을 작성한 후 실행한다. 
sql = "select * from member"
cursor.execute(sql)
print("전체회원출력")
#회원수만큼 반복해서 출력한다. 
for rs in cursor:
    #컬럼에 접근시에는 인덱스 0부터 시작한다. 
    print(rs[0], rs[1], rs[2], rs[3])

#인파라미터가 있는 동적쿼리문은 :(콜론)을 변수앞에 붙여준다.
sql = "select * from member where id=:userid"
#앞에서 선언한 변수에 값을 설정한 후 실행한다. 
cursor.execute(sql, userid='test1')
#fetchone() : 하나의 레코드를 인출한다. 
member = cursor.fetchone()
print("\ntest1 회원출력")
#서식문자를 이용해서 레코드를 출력한다. 
print("%s %s %s %s" % (member[0], member[1], member[2], member[3]))

#인서트를 위한 데이터를 준비한다. 
my_tit = "셀레니움 크롤링 좋아요2"
my_con = "크롤링 엄청 잘되네"
my_id = "musthave"
#두줄 이상의 쿼리문 작성시에는 블럭단위 주석과 동일하게 기술한다. 
#인파라미터는 ':변수명'과 같이 작성한다. 
sql = """insert into board (num,title,content,id,postdate,visitcount)
        values (seq_board_num.nextval, :title, :content, :userid, 
                sysdate, 0)"""
try:
    #쿼리문 실행시 인파라미터를 설정한다. 
    cursor.execute(sql, title=my_tit, content=my_con, userid=my_id)
    #쿼리 실행에 문제가 없다면 커밋해서 실제 테이블에 반영한다. 
    conn.commit()
    print("1개의 레코드 입력")
except Exception as e:    
    #예외가 발생하면 롤백처리한다. 
    conn.rollback()
    print("insert 실행시 오류발생", e)
#연결 해제 
conn.close()


