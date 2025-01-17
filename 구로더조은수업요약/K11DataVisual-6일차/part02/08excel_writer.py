# -*- coding: utf-8 -*-
import pandas as pd

#문자형 및 숫자형 데이터를 딕셔너리로 정의한다. 
data1 = {'name' : [ 'Jerry', 'Riah', 'Paul'],
         'algol' : [ "A", "A+", "B"],
         'basic' : [ "C", "B", "B+"],
         'c++' : [ "B+", "C", "C+"]}
data2 = {'c0':[1,2,3], 
         'c1':[4,5,6], 
         'c2':[7,8,9], 
         'c3':[10,11,12], 
         'c4':[13,14,15]}

#데이터프레임으로 변환 후 첫번째 컬럼으로 인덱스를 지정한다. 
df1 = pd.DataFrame(data1)
#inplace 옵션으로 원본 데이터프레임에 적용한다. 
df1.set_index('name', inplace=True)      
print(df1)
print('\n')

df2 = pd.DataFrame(data2)
df2.set_index('c0', inplace=True)        
print(df2)

#각 데이터프레임을 지정한 sheet에 저장한다. 
writer = pd.ExcelWriter("./save/df_excelwriter.xlsx")
#to_excel() 함수의 두번째 인수로 sheet를 지정한다. 
df1.to_excel(writer, sheet_name="sheet1")
df2.to_excel(writer, sheet_name="sheet2")
#sheet를 지정한 후 저장하는 경우 save()함수를 추가로 실행한다. 
writer.save()

