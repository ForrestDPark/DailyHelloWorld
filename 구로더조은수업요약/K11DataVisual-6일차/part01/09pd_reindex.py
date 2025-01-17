# -*- coding: utf-8 -*-
import pandas as pd

#인덱스를 지정한 상태로 데이터프레임을 생성한다. 
dict_data = {'c0':[1,2,3], 'c1':[4,5,6], 'c2':[7,8,9], 
             'c3':[10,11,12], 'c4':[13,14,15]}
df = pd.DataFrame(dict_data, index=['r0', 'r1', 'r2'])
print(df)

'''
reindex()
: 데이터프레임의 행 인덱스를 새로운 배열로 재지정한다. 기존 객체를
변경하지 않고 새로운 객체를 반환한다. 만약 존재하지 않는 인덱스를 
지정하면 해당 행은 NaN으로 초기화된다. 

reset_index()
: 행 인덱스를 정수형 위치 인덱스로 초기화한다. 기존 행 인덱스는 열로
이동한다. reindex()와 동일하게 새로운 객체를 반환한다. 
'''
#인덱스로 사용할 리스트를 선언한다. 
new_index = ['r0', 'r1', 'r2', 'r3', 'r4']
#인덱스를 재부여한다. 단 r3, r4는 데이터가 없으므로 NaN으로 초기화된다.
ndf = df.reindex(new_index)
print(ndf)

#앞과 동일하게 인덱스를 재지정한다. 단 NaN인 부분에 0으로 대체해서 
#초기화한다. fill_value옵션은 디폴트값을 부여해준다. 
new_index = ['r0', 'r1', 'r2', 'r3', 'r4']
ndf2 = df.reindex(new_index, fill_value=0)
print(ndf2)

#정수형 위치 인덱스로 초기화된다. 기존의 인덱스는 데이터로 복원된다. 
ndf3 = ndf2.reset_index()
print(ndf3)

'''
sort_index()
: 행 인덱스를 기준으로 값을 정렬한다. ascending 옵션으로 
True(오름차순), False(내림차순) 정렬을 할 수 있다. 

sort_value()
: 열을 기준으로 정렬한다. 옵션은 동일하다. 
'''
#정수형 인덱스를 내림차순으로 정렬한다. 
ndf4 = ndf3.sort_index(ascending=False)
print(ndf4)

#C3열을 기준으로 오름차순 정렬한다. 
ndf5 = ndf4.sort_values(by='c3', ascending=True)
print(ndf5)









