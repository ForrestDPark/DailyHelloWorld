# -*- coding: utf-8 -*-
import pandas as pd

#딕셔너리 정의 및 데이터프레임 생성
exam_data = {'국어' : [ 90, 80, 70], 
             '영어' : [ 98, 89, 95],
             '수학' : [ 85, 95, 100], 
             '체육' : [ 100, 90, 90]}
#생성시 인덱스를 지정한다. 
df = pd.DataFrame(exam_data, index=['유비', '관우', '장비'])
print(df, '\n')     

'''
행(row)선택
    loc : 인덱스명을 기준으로 행을 선택한다. 선택한 모든
        범위가 포함된다. 
    iloc : 정수형 위치 인덱스를 통해 행을 선택한다. 마지막
        부분은 제외된다. 
'''
# 첫번째 행을 선택해서 출력
label1 = df.loc['유비'] 
print(label1, '\n')
# 두번째 행을 선택해서 출력
position1 = df.iloc[1]  
print(position1, '\n')

'''
행 인덱스를 사용해서 2개 이상의 행을 선택한다. 범위아님.
아래 2개의 문장은 동일한 결과를 출력한다. 
'''
label2 = df.loc[['유비', '장비']]
print(label2, '\n')
position2 = df.iloc[[0, 2]]
print(position2, '\n')

'''범위를 지정해서 선택한다. 인덱스명을 사용하는 경우
마지막 부분이 포함된다. '''
label3 = df.loc['유비':'장비']
#2개의 행이 출력된다. 
print(label3, '\n')  
#정수형 인덱스는 마지막이 포함되지 않으므로 1개만 출력된다.
position3 = df.iloc[0:1]
print(position3, '\n')  


'''
열(Column)선택
: 열을 선택할때는 대괄호를 사용하거나, 닷(.)을 사용한다. 
닷을 사용할경우 열 이름이 문자형이어야 한다. 
시리즈 객체를 반환한다. 
'''
#대괄호를 통해 수학 컬럼을 선택한 후 출력
math1 = df['수학'] 
print(math1, '\n')

#닷을 사용해서 선택
english = df.영어 
print(english, '\n')
print(type(english), '\n')  

#2개 이상의 열 선택
column1 = df[['국어', '체육']]
print(column1, '\n')
#데이터프레임 객체 반환
print(type(column1), '\n')  

#1개의 열을 선택했지만, 원소가 리스트로 주어졌으므로 
#데이터프레임 객체로 반환된다. 
math2 = df[['수학']]
print(math2, '\n')
print(type(math2), '\n')






