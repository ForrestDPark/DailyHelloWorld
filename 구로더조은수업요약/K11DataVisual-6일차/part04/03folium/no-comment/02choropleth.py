# -*- coding: utf-8 -*-
import pandas as pd
import folium
import json
 
file_path = '../data/경기도인구데이터.xlsx'
df = pd.read_excel(file_path, index_col='구분', engine= 'openpyxl')  
df.columns = df.columns.map(str)

geo_path = '../data/경기도행정구역경계.json'
try:
    geo_data = json.load(open(geo_path, encoding='utf-8'))
except:
    geo_data = json.load(open(geo_path, encoding='utf-8-sig'))

g_map = folium.Map(location=[37.5502,126.982], 
                   tiles='Stamen Terrain', zoom_start=9)

year = '2017'  
folium.Choropleth(geo_data=geo_data,  
                 data = df[year],      
                 columns = [df.index, df[year]],   
                 fill_color='PuBuGn', fill_opacity=0.7, line_opacity=1,                           
                 key_on='feature.properties.name',  
                 legend_name='경기도인구데이터',
                 ).add_to(g_map)
 
g_map.save('../save/gyonggi_population_' + year + '.html')

