# -*- coding: utf-8 -*-
 
import os
import sys
import urllib.request
import json
import pandas as pd

# Naver API Key입력
client_id = "6VTiJdjKGycNDkOw8KUY"
client_secret = "rEDK8jnsHl"
# 검색어
encText = urllib.parse.quote("JSP책")
url = "https://openapi.naver.com/v1/search/blog?query=" + encText # json 결과
# url = "https://openapi.naver.com/v1/search/blog.xml?query=" + encText # xml 결과
request = urllib.request.Request(url)
request.add_header("X-Naver-Client-Id",client_id)
request.add_header("X-Naver-Client-Secret",client_secret)
response = urllib.request.urlopen(request)
rescode = response.getcode()
if(rescode==200):
    response_body = response.read()
    result = response_body.decode('utf-8')
else:
    print("Error Code:" + rescode)

# 파싱한 정보를 저장할 리스트 정의 
title = []
bloggername = []
bloggerlink = []
# 네이버 검색 결과를 json으로 받아온다. 파싱을 위해 loads()
# 함수를 사용한다. 
json_data = json.loads(result)
# items에 저장된 배열의 크기만큼 반복하면서 파싱한다. 
for item in json_data['items']:
    #print(item['title'])
    # 파싱된 정보는 리스트에 추가한다. 
    title.append(item['title'])
    bloggername.append(item['bloggername'])
    bloggerlink.append(item['bloggerlink'])

# 리스트에 저장된 정보를 기반으로 딕셔너리를 생성하고 이것을 
# 데이터프레임으로 변환한다. 
df = pd.DataFrame({'제목':title, '작성자':bloggername, '링크':bloggerlink})
print(df)

#인덱스를 추가한 후 엑셀로 변환한다. 
df.set_index('제목', inplace=True)
df.to_excel("./save/JSP검색결과.xlsx")    
    
    
    
    
    
    
    
    
    
    
    
    
    