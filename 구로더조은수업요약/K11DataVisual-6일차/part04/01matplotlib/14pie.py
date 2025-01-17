# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
'''
파이차트 
: 원을 파이조각처럼 나누어 표현한다. 데이터의 크기가 클수록
파이의 크기도 크게 표현된다. 
'''
df = pd.read_csv('../data/auto-mpg.csv', header=None)

plt.style.use('default')   

df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']
'''
데이터 갯수를 카운트하기 위해 값 1을 가진 열을 추가한다. 
origin열은 제조국가를 표시하는 컬럼으로 1:USA, 2:EU, 3:JPN을 나타낸다.
origin열을 기준으로 그룹화 한 후 합계 연산한 결과를 파이차트로 표현한다.
'''
df['count'] = 1
df_origin = df.groupby('origin').sum()
#제조국가별로 모든 행에 대해 합계가 된 결과를 볼수있다. 
print(df_origin.head())

#제조국가(Origin) 값을 실제 국가명으로 변경하기 위해 인덱스로 지정한다. 
df_origin.index = ['USA', 'EU', 'JAPAN']

#합계한 결과(count열)를 통해 파이차트를 생성한다. 
'''
autopct : 퍼센트(%)를 표시한다. 소수 이하 첫째자리까지 표현한다.
    만약 1.2f가 되면 소수 이하 둘째자리까지 표현한다. 
startangle : 파이 조각을 나누는 시작점으로 각도를 표시한다. 
'''
df_origin['count'].plot(kind='pie', 
                     figsize=(7, 5),
                     autopct='%1.2f%%',
                     startangle=10,
                     colors=['chocolate', 'bisque', 'cadetblue']
                     )
#타이틀 표시
plt.title('Model Origin', size=20)
#파이 차트의 비율을 원에 가깝게 조정한다.
plt.axis('equal')
#범례를 표시
plt.legend(labels=df_origin.index, loc='upper right')
plt.show()
