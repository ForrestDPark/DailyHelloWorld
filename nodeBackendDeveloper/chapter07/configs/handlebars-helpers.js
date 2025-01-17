// configs/handlebars-helpers.js

module.exports = {
    // (1) list 길이 반환
    lengthOfList: (list = []) => list.length,
    // (2) 두값 비교하여 같은지 여부 반환 
    eq: (val1, val2) => val1 === val2,
    // (3) ISO 날짜 문자열에서 날짜만 반환 
    dateString: (isoString) => new Date(isoString).toLocaleDateString(),
}