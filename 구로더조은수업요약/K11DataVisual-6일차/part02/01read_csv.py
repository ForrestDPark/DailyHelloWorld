# -*- coding: utf-8 -*-
import pandas as pd
'''
CSV(Comma-separated values) 
: 텍스트 파일의 일종으로 쉼표(,)로 열을 구분하고 엔터로 행을
구분한다. 엑셀로 주로 생성한다. 
''' 
# csv파일의 경로를 지정한다. 
file_path = './data/read_csv_sample.csv'

'''
read_csv() : CSV 파일을 데이터프레임으로 변환한다. 별도의 옵션이
    없으면 첫번째행은 제목으로 간주한다. '''
df1 = pd.read_csv(file_path)
print(df1)

'''
header : 열의 이름으로 사용될 행의 번호를 지정한다. 기본값은 0이다. 
    만약 첫행부터 데이터가 있다면 None으로 지정하면 된다. 
'''
df2 = pd.read_csv(file_path, header=None)
print(df2)

# index_col : 행의 인덱스로 사용할 열의 번호
#정수형 인덱스로 지정된다. 
df3 = pd.read_csv(file_path, index_col=None)
print(df3)
#c0 컬럼이 인덱스로 지정된다. 
df4 = pd.read_csv(file_path, index_col='c0')
print(df4)

#names : 열의 이름으로 사용할 문자열 리스트
df5 = pd.read_csv(file_path, names=['손오공','저팔계','사오정'])
print(df5)

#skiprows : 처음 몇줄을 skip 할지를 설정한다. 
df6 = pd.read_csv(file_path, skiprows=2)
print(df6)

