# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt

from matplotlib import font_manager, rc
font_path = "../data/malgun.ttf"
font_name = font_manager.FontProperties(fname=font_path).get_name()
rc('font', family=font_name)

df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', engine='openpyxl', header=0)
df = df.fillna(method='ffill')
print(df.head())

mask = (df['전출지별']=='서울특별시') & (df['전입지별']!='서울특별시')
df_seoul = df[mask]
df_seoul = df_seoul.drop(['전출지별'], axis=1)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
df_seoul.set_index('전입지', inplace=True)
print(df_seoul)
sr_one = df_seoul.loc['경기도']
print(sr_one)

plt.style.use('ggplot')
plt.figure(figsize=(14, 5))  
plt.xticks(rotation='vertical')
plt.plot(sr_one.index, sr_one.values, marker='o', markersize=10) 

plt.title('서울 -> 경기 인구 이동')
plt.xlabel('기간')
plt.ylabel('이동 인구수')
plt.legend(labels=['서울->경기'], loc='best') 

plt.ylim(50000, 800000)

plt.annotate('',
             xytext=(2, 290000),   
             xy=(20, 620000),      
             xycoords='data',       
             arrowprops=dict(arrowstyle='->', color='skyblue', lw=2),
             )  
plt.annotate('',
             xytext=(30, 580000),   
             xy=(47, 450000),       
             xycoords='data',       
             arrowprops=dict(arrowstyle='->', color='olive', lw=5), 
             )
plt.annotate('인구이동 증가(1970-1995)',  
             xy=(10, 450000),           
             rotation=25,                
             va='baseline',            
             ha='center',               
             fontsize=15,                
             )
plt.annotate('인구이동 감소(1995-2017)', 
             xy=(40, 560000),           
             rotation=-10,              
             va='baseline',             
             ha='center',              
             fontsize=15,              
             )

plt.show() 














