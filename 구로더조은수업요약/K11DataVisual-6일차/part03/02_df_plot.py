# -*- coding: utf-8 -*-
import pandas as pd

#엑셀을 데이터프레임으로 변환한다. 
df = pd.read_excel('./data/남북한발전전력량.xlsx', engine='openpyxl')  

'''
데이터프레임으로 변환시 header옵션이 없으므로 첫행은 컬럼명
으로 인식한다. 따라서 두번째행부터 가져오게된다. 
[0,5] => 엑셀의 2행과 7행을 의미한다. 
3: => D열부터 마지막을 의미하므로 1991년부터 끝까지 선택
해서 변수에 저장한다. 
''' 
df_ns = df.iloc[[0, 5], 3:]
#남북한 데이터에 인덱스를 부여한다.             
df_ns.index = ['South','North'] 
#열 이름의 자료형을 정수형으로 변경한다.       
df_ns.columns = df_ns.columns.map(int) 
print(df_ns.head())

#선 그래프1
df_ns.plot()

#선 그래프2 
'''클래스 속성인 T를 이용해서 데이터프레임을 전치한다. 
즉 행과 열을 바꾸는것을 말한다. 전치된 데이터를 통해 선
그래프를 출력한다. '''
tdf_ns = df_ns.T 
print(tdf_ns.head())
tdf_ns.plot()

#막대 그래프
df_ns.plot(kind='bar')
tdf_ns.plot(kind='bar')

 





