// configs/mongodb-connection.js 

// (1) MongoDB ACCESS 를 위한 빈 client 객체와 version 정보 객체 import
const { MongoClient, ServerApiVersion } = require("mongodb")

// (2) 기본 db 생성( 첫데이터 추가시 지정한 데이터베이스 자동 생성) 하는 url
const url = "mongodb+srv://pulpilisory:qwe123@cluster0.kbog4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0";

// (3) client 객체에 url 과 version 정보 채우기 
const client = new MongoClient(url, {
  serverApi: {
    version: ServerApiVersion.v1,
    strict: true, // 지원하지 않는 기능이나 연산자 사용시 에러 발생 하도록 함. 
    deprecationErrors: true, // 최신 버전에서 사용하지 않는 deprecate 기능을 사용하려할때 경고대신 에러 발생
  }
});

// (4) client 정보로 connection 하고 난뒤의 결과값 을 반환 
module.exports = function (callback){
    // 몽고디비 커넥션 연결 함수 반환
    return client.connect(url,callback)
}