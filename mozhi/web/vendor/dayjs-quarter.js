/**
 * Bundled by jsDelivr using Rollup v4.62.2 and esbuild v0.28.1.
 * Original file: /npm/dayjs@1.11.13/plugin/quarterOfYear.js
 *
 * Do NOT use SRI with dynamically generated files! More information: https://www.jsdelivr.com/using-sri-with-dynamic-files
 */
var u={exports:{}},v=u.exports,o;function c(){return o||(o=1,(function(f,x){(function(e,n){f.exports=n()})(v,(function(){var e="month",n="quarter";return function(m,h){var a=h.prototype;a.quarter=function(t){return this.$utils().u(t)?Math.ceil((this.month()+1)/3):this.month(this.month()%3+3*(t-1))};var d=a.add;a.add=function(t,r){return t=Number(t),this.$utils().p(r)===n?this.add(3*t,e):d.bind(this)(t,r)};var p=a.startOf;a.startOf=function(t,r){var s=this.$utils(),O=!!s.u(r)||r;if(s.p(t)===n){var i=this.quarter()-1;return O?this.month(3*i).startOf(e).startOf("day"):this.month(3*i+2).endOf(e).endOf("day")}return p.bind(this)(t,r)}}}))})(u)),u.exports}var q=c();export{q as default};
//# sourceMappingURL=/sm/56cc73899968cff28d2253ef525928485907f92cb7d154ce3da0a9c565ca6246.map