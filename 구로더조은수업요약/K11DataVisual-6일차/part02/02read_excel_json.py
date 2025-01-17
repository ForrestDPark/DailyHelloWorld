# -*- coding: utf-8 -*-
import pandas as pd

'''
read_excel() 메서드로 데이터프레임 변환. 첫행은 타이틀로 인식한다. 
즉 header=0을 디폴트로 사용한다. 
'''
df1 = pd.read_excel('./data/남북한발전전력량.xlsx', engine='openpyxl')
print(df1)

'''
데이터를 가져오는것은 df1과 동일하지만 타이틀이 없는것으로 간주하여
정수형 컬럼명이 타이틀로 추가된다. 
'''
df2 = pd.read_excel('./data/남북한발전전력량.xlsx', engine='openpyxl', 
                    header=None)  
print(df2)

'''
header=1은 인덱스 1을 타이틀로 간주하겠다는 의미이므로 2행이 타이틀로
인식되어 데이터프레임으로 변환된다. 
'''
df3 = pd.read_excel('./data/남북한발전전력량.xlsx', engine='openpyxl', 
                    header=1)  
print(df3)

# JSON파일을 데이터프레임으로 변환한다. 
df4 = pd.read_json('./data/read_json_sample.json')  
print(df4)
#인덱스만 출력한다. 
print(df4.index)

