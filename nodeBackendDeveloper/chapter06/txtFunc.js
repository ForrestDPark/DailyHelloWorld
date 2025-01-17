function r(str) {
    console.log('\x1b[31m%s\x1b[0m', str);
  }
  
  function y(str) {
    console.log('\x1b[33m%s\x1b[0m', str);
  }
  
  function g(str) {
    console.log('\x1b[32m%s\x1b[0m', str);
  }
  
  function b(str) {
    console.log('\x1b[36m%s\x1b[0m', str);
  }
  
  function bold(str){
      console.log('\x1b[1m%s\x1b[0m', str);
  }
  
  function underline(str){
      console.log('\x1b[4m%s\x1b[0m', str);
  }
  
  function reverse(str){
      console.log('\x1b[7m%s\x1b[0m', str);
  }
  
  function bgRed(str){
      console.log('\x1b[41m%s\x1b[0m', str);
  }
  
  function bgGreen(str){
      console.log('\x1b[42m%s\x1b[0m', str);
  }
  module.exports = { r, y, g, b, bold, underline, reverse, bgRed, bgGreen };