#모듈 임포트
import cx_Oracle as cx
import folium

#오라클 연결
host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
connect_info = cx.makedsn(host_name, oracle_port, service_name)
conn = cx.connect('study', '1234', connect_info)
cursor = conn.cursor()

#경기권의 맵 생성
univ_map = folium.Map(location=[37.40, 127.38], zoom_start=10)
univ_map.save('../save/univ_map.html')

#테이블에 입력된 대학정보를 인출한다. 
sql = "select * from g_univ order by idx asc"
cursor.execute(sql)
for rs in cursor:
    idx = rs[0]
    sigun = rs[1]
    faclt = rs[2]
    addr = rs[3]     
    latitude = rs[4]
    longitude = rs[5]
    #인출된 정보 중 위,경도를 이용해서 지도에 마커를 추가한다. 
    folium.Marker([latitude,longitude], popup=faclt).add_to(univ_map)
    print(faclt, latitude, longitude)
#마커가 추가된 지도를 파일로 저장한다.             
univ_map.save('../save/univ_map_marker.html')
print("맵이 생성되었습니다.")  

 