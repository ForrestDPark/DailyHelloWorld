# -*- coding: utf-8 -*- 
import pandas as pd
'''
산점도 : 두 변수의 관계를 점으로 표현한 그래프
박스플롯 : 특정 변수의 데이터 분포와 분산정도에 대한 정보를 제공하는
    그래프
'''
#자동차 연비 데이터를 데이터프레임으로 변환하고 컬럼을 지정한다. 
df = pd.read_csv('./data/auto-mpg.csv', header=None)
df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

'''
2개의 열을 선택해서 산점도를 그린다. 
차량의 무게가 클수록 연비는 낮아지는 경향을 보인다. 
즉 이 둘의 관계는 역(-)의 상관관계를 갖는다. 
'''
df.plot(x='weight',y='mpg', kind='scatter')

'''
연비와 실린더 컬럼을 선택해서 박스플롯을 그린다. 
연비의 경우 10~45범위에 넓게 분포된것을 관찰할 수 있다. 
상단에 o로 표시되는 이상치도 관측되는데, 보통 관측되는 데이터의 
범위에서 많이 벗어난 값을 말한다. 
'''
df[['mpg','cylinders']].plot(kind='box')

