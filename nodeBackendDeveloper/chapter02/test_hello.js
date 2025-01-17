
// console.log("안녕하세요 ")

getToken()
function getToken(){
    var result = String(Math.floor(Math.random()*100000)).padStart(6,"0")
    console.log(result)
}
function func1() {
    console.log("1")
    func2();
    return;
}
function func2() {
    console.log("2")
    return;
}

// func1();


// Server test 10초동안 100명이 서버 접속
import http from 'k6/http';

export const options={
    vus :200,
    duration : "10s",
};

export default function(){
    http.get("http://localhost:8000");
    sleep(1)
}