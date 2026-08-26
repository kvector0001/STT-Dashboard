"use strict";

const fs = require("fs");
const vm = require("vm");


function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() not found`);
  const bodyStart = source.indexOf("{", start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}


const source = fs.readFileSync("index.html", "utf8");
const summarizeSource = extractFunction(source, "summarize");
const stocks = [
  { quantity: 1, buy_avg: 90, ltp: 110, ret_1m: 10 },
  { quantity: 100, buy_avg: 100, ltp: 100, ret_1m: null },
];
const context = { stocks };
vm.runInNewContext(`${summarizeSource}; result = summarize(stocks);`, context);

if (Math.abs(context.result.m1Pct - 10) > 1e-9) {
  throw new Error(`Expected 10% from the one valid holding, got ${context.result.m1Pct}%`);
}
console.log("PASS null returns are excluded from summary weighting");