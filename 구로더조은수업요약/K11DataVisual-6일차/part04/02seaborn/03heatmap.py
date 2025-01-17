# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns
'''
히트맵 : 히트맵은 열을 뜻하는 히트(Heat)와 지도를 뜻하는 맵(Map)을
    결합시킨 단어로, 색상으로 표현할 수 있는 다양한 정보를 일정한 
    이미지 위에 열분포 형태의 비쥬얼한 그래픽으로 출력한다. 
'''
titanic = sns.load_dataset('titanic')
sns.set_style('darkgrid')

'''
데이터프레임을 피벗테이블로 정리할때 한 변수(sex)를 행 인덱스로
나머지 변수(class)를 열 이름으로 설정한다. 
aggfunc='size' 옵션은 데이터값의 크기를 기준으로 집계한다는 의미이다.
'''
table = titanic.pivot_table(index=['sex'], columns=['class'], 
                            aggfunc='size')

'''
히트맵 그리기
    table : 데이터프레임
    annot=True : 데이터값 표시 여부
    fmt='d' : 정수형 포맷으로 설정
    cmap : 컬러맵
    lineWidth : 구분선의 두께
    cbar : 컬러바 표시여부(False이면 표시하지 않음)

컬러맵 참조
https://matplotlib.org/stable/tutorials/colors/colormaps.html    
['Greys', 'Purples', 'Blues', 'Greens', 'Oranges', 'Reds',
'YlOrBr', 'YlOrRd', 'OrRd', 'PuRd', 'RdPu', 'BuPu',
'GnBu', 'PuBu', 'YlGnBu', 'PuBuGn', 'BuGn', 'YlGn'])
'''
sns.heatmap(table, annot=True, fmt='d', cmap='YlGnBu', 
    linewidth=.5, cbar=False)
#sns.heatmap(table, annot=True, fmt='d', cmap='YlGnBu', 
#            linewidth=.5, cbar=True)

plt.show()




