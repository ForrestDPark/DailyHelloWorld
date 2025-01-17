# -*- coding: utf-8 -*-
import folium
'''
Folium라이브러리 - 지도활용
: 코드를 실행하면 IDE에서 직접 지도가 표시되지 않고, HTML파일로 
저장한 후 웹브라우저를 통해 확인할 수 있다. open externally 메뉴로
실행할 수 있다. 
'''
#기본맵 : 인자로 시설물의 위,경도 그리고 줌 레벨을 지정한다. 
seoul_map1 = folium.Map(location=[37.55,126.98], zoom_start=12)
seoul_map1.save('../save/seoul1.html')
#Stamen Terrain : 산악 지형 들이 선명하게 표현된다. 
seoul_map2 = folium.Map(location=[37.55,126.98], zoom_start=12, 
                        tiles='Stamen Terrain')
seoul_map2.save('../save/seoul2.html')
#Stamen Toner : 흑백 스타일로 도로망을 강조한다. 
seoul_map3 = folium.Map(location=[37.55,126.98], zoom_start=15, 
                        tiles='Stamen Toner')
seoul_map3.save('../save/seoul3.html')

#데이터프레임 변환을 위해 pandas모듈 임포트
import pandas as pd
#별다른 옵션이 없으므로 2행부터 데이터프레임으로 변환된다. 
df = pd.read_excel('../data/서울지역 대학교 위치.xlsx', 
                   engine='openpyxl')
#컬럼명을 지정한다. 
df.columns = ['학교명', '위도', '경도'] 
#데이터프레임에 저장된 학교의 갯수만큼 반복하여 지도에 마커를 추가한다.
for name, lat, lng in zip(df.학교명, df.위도, df.경도):
    #위경도는 리스트로 부여하고, popup(풍선도움말)에는 학교명을 지정한다.
    folium.Marker([lat,lng], popup=name).add_to(seoul_map2)
seoul_map2.save('../save/seoul_colleges1.html')

#원형마커 및 추가적인 옵션을 지정한다. 
for name, lat, lng in zip(df.학교명, df.위도, df.경도):
    folium.CircleMarker([lat,lng], radius=10, color='brown', 
                        fill=True, fill_color='coral', 
                        fill_opacity=0.7, popup=name).add_to(seoul_map3)
seoul_map3.save('../save/seoul_colleges2.html')    


