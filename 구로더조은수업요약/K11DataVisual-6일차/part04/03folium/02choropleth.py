# -*- coding: utf-8 -*-
import pandas as pd
import folium
import json
'''
Choropleth Map(코로프레스 맵) : 행정구역과 같이 지도상의 경계를 
    표시해준다. 
''' 
#경기도의 인구데이터를 데이터프레임으로 변환한다. 
file_path = '../data/경기도인구데이터.xlsx'
df = pd.read_excel(file_path, index_col='구분', engine= 'openpyxl')  
df.columns = df.columns.map(str)

#경기도 시군구 경계 정보를 가진 geo-json 파일을 불러온다. 
#행정구역이 위경도를 통해 표현되어있다. 
geo_path = '../data/경기도행정구역경계.json'
try:
    geo_data = json.load(open(geo_path, encoding='utf-8'))
except:
    geo_data = json.load(open(geo_path, encoding='utf-8-sig'))
#폴리엄을 통해 경기도 지도를 생성한다. 산악지형을 강조하는 맵으로 생성한다.
g_map = folium.Map(location=[37.5502,126.982], 
                   tiles='Stamen Terrain', zoom_start=9)
#출력할 연도는 2017년으로 선택한다.(2007~2017까지 선택가능) 
'''
geo_data : 지도 데이터 혹은 파일의 경로
data : 시각화 하고자 하는 데이터파일(여기서는 데이터프레임)
columns : 지도 데이터와 매핑할 값. 시작화할 변수를 지정.
fill_color : 시각화에 사용할 색상
fill_opacity, line_opacity : 투명도
key_on : 데이터파일과 매핑할 값
legend_name : 범례표시
'''
year = '2017'  
folium.Choropleth(geo_data=geo_data,  
                 data = df[year],      
                 columns = [df.index, df[year]],   
                 fill_color='PuBuGn', fill_opacity=0.7, line_opacity=1,                           
                 key_on='feature.properties.name',  
                 legend_name='경기도인구데이터',
                 ).add_to(g_map)
 
g_map.save('../save/gyonggi_population_' + year + '.html')
'''
fill_color속성에 들어가는 색상값들은 folium내 utilities라는 파일이 
이미 정의되어있다. 내용은 아래와 같다. 
'BuGn': 'Sequential',
'BuPu': 'Sequential',
'GnBu': 'Sequential',
'OrRd': 'Sequential',
'PuBu': 'Sequential',
'PuBuGn': 'Sequential',
'PuRd': 'Sequential',
'RdPu': 'Sequential',
'YlGn': 'Sequential',
'YlGnBu': 'Sequential',
'YlOrBr': 'Sequential',
'YlOrRd': 'Sequential',
'BrBg': 'Diverging',
'PiYG': 'Diverging',
'PRGn': 'Diverging',
'PuOr': 'Diverging',
'RdBu': 'Diverging',
'RdGy': 'Diverging',
'RdYlBu': 'Diverging',
'RdYlGn': 'Diverging',
'Spectral': 'Diverging',
'Accent': 'Qualitative',
'Dark2': 'Qualitative',
'Paired': 'Qualitative',
'Pastel1': 'Qualitative',
'Pastel2': 'Qualitative',
'Set1': 'Qualitative',
'Set2': 'Qualitative',
'Set3': 'Qualitative'
'''
