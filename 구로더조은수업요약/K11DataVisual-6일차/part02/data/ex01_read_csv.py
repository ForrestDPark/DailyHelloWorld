# -*- coding: utf-8 -*-
"""
Created on Sun Mar 27 19:25:15 2022

@author: user
"""
# 라이브러리 불러오기
import pandas as pd

# 파일경로를 찾고, 변수 file_path에 저장
file_path = 'read_csv_sample.csv'

# read_csv() 함수로 데이터프레임 변환. 변수 df1에 저장
df1 = pd.read_csv(file_path)
print(df1)


