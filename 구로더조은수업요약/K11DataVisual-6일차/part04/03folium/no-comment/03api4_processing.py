import cx_Oracle as cx
import folium

host_name = 'localhost'
oracle_port = 1521
service_name = 'xe'
connect_info = cx.makedsn(host_name, oracle_port, service_name)
conn = cx.connect('kosmo', '1234', connect_info)
cursor = conn.cursor()

univ_map = folium.Map(location=[37.40,127.38], zoom_start=10)
univ_map.save('../save/univ_map.html')

sql = "select * from g_univ order by idx asc"
cursor.execute(sql)
for rs in cursor:
    idx = rs[0]
    sigun = rs[1]
    faclt = rs[2]
    addr = rs[3]     
    latitude = rs[4]
    longitude = rs[5]
    folium.Marker([latitude,longitude], popup=faclt).add_to(univ_map)
    print(faclt, latitude, longitude)
            
univ_map.save('../save/univ_map_marker.html')
print("맵이 생성되었습니다.")  

 