# -*- coding: utf-8 -*-
'''

'''
import squarify
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

def sub_addr(x, i):
    x2 = x.split()
    return x2[i].strip()

input_file = "../data/서울특별시_종로구_치킨집.csv"
df_chicken1 = pd.read_csv(input_file)
print(df_chicken1.info())
print(df_chicken1.head())

#결측치제거
df_chicken1 = df_chicken1.dropna(axis=0)

#코딩하기 편한 변수명으로 변
df_chicken1.columns = ['addr', 'name']
print(df_chicken1.info())
print(df_chicken1.head())

#소재지 전체주소 열에서 구 추출
df_chicken1['addr2'] = df_chicken1['addr'].apply(lambda x: sub_addr(x, 1))
print(df_chicken1['addr2'].head(10))

#소재지 전체주소 열에서 동 추출
df_chicken1['addr3'] = df_chicken1['addr'].apply(lambda x: sub_addr(x, 2))
print(df_chicken1['addr3'].head(10))

df_chicken2 = df_chicken1[df_chicken1['addr2']=='종로구']

#빈도(도수분포)표 작성 후 데이터프레임으로 변환
df_chicken3 = df_chicken2.groupby('addr3')[['addr3']].count()

df_chicken3 = df_chicken3.rename(columns={'addr3':'count'}, inplace=False)
df_chicken3 = df_chicken3.sort_values(by='count', ascending=False)

df_chicken3["name"] = df_chicken3.index
df_chicken3.index = range(70)

df_chicken4 = df_chicken3.head(30)

#그래프의 스타일과 폰트지정
plt.style.use('ggplot')
font_name = font_manager.FontProperties(fname="../data/malgun.ttf").get_name()
rc('font', family=font_name)

#기본틀 만들기
ax = plt.subplot()
df_chicken4["label"] = df_chicken4['name']+"\n("+df_chicken4['count'].astype(str)+")"

ax = squarify.plot(sizes=df_chicken4['count'], label=df_chicken4['label'], alpha=.8)
plt.axis('off')
plt.savefig('../save/chicken01.png', dpi=300, bbox_inches='tight')
plt.show()






