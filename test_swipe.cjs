const test = require('node:test');
const assert = require('node:assert/strict');
const {choice} = require('./swipe.js');
test('comfortable distance commits in either direction on a phone', () => {
  assert.equal(choice(85, 12, 380, .1), null);
  assert.equal(choice(90, 12, 380, .1), 'keep');
  assert.equal(choice(-90, 12, 380, -.1), 'pass');
});
test('quick short flick commits without a full drag', () => {
  assert.equal(choice(40, 4, 380, .6), 'keep');
  assert.equal(choice(-40, 4, 380, -.6), 'pass');
});
test('tiny motion, vertical scrolling and opposite velocity do not commit', () => {
  assert.equal(choice(15, 0, 380, 1), null);
  assert.equal(choice(100, 150, 380, 1), null);
  assert.equal(choice(40, 4, 380, -.6), null);
});
test('desktop threshold remains reachable and compact screens scale down', () => {
  assert.equal(choice(91, 0, 560, 0), 'keep');
  assert.equal(choice(72, 0, 300, 0), 'keep');
});

// Simulates the event lifecycle, including the child capture-loss event that
// Android touch input can bubble up when capture transfers to the card.
function fixture({scrollable = false} = {}) {
  const listeners = {}, moves = [], releases = [], active = [];
  let cancelled = 0, captured = false;
  const card = {
    clientWidth:380,
    addEventListener(name, fn) {listeners[name] = fn;},
    setPointerCapture() {captured = true;},
    hasPointerCapture() {return captured;},
    releasePointerCapture(id) {
      captured = false;
      listeners.lostpointercapture({target:card, pointerId:id});
    }
  };
  const child = {closest: () => null};
  const controller = require('./swipe.js').attach(card, {
    canStart: e => !e.target.closest('button'), isScrollTarget: () => scrollable, onActive:x=>active.push(x),
    onMove:(...x)=>moves.push(x), onRelease:x=>releases.push(x), onCancel:()=>cancelled++
  });
  function emit(type, overrides={}) {
    listeners[type]({target:child, pointerId:1, isPrimary:true, button:0,
      clientX:0, clientY:0, timeStamp:0, ...overrides});
  }
  return {card,child,emit,moves,releases,active,controller,get cancelled(){return cancelled;}};
}
test('child capture-loss does not abort an Android swipe', () => {
  const f = fixture();
  f.emit('pointerdown');
  f.emit('lostpointercapture'); // implicit capture moves from title to card
  f.emit('pointermove', {clientX:100, clientY:8,timeStamp:100});
  f.emit('pointerup', {clientX:100,clientY:8,timeStamp:110});
  assert.deepEqual(f.moves, [[100,8]]);
  assert.deepEqual(f.releases,['keep']);
  assert.equal(f.cancelled,0);
  assert.deepEqual(f.active,[true,false]);
});
test('capture loss on the card and pointer cancellation reset safely', () => {
  for (const type of ['lostpointercapture','pointercancel']) {
    const f=fixture(); f.emit('pointerdown');
    f.emit(type,{target:f.card});
    f.emit('pointerup',{clientX:150,timeStamp:100});
    assert.equal(f.cancelled,1);
    assert.deepEqual(f.releases,[]);
  }
});
test('short drag springs back, a new drag works, and another finger is ignored', () => {
  const f=fixture();f.emit('pointerdown');
  f.emit('pointermove',{clientX:20,timeStamp:100});
  f.emit('pointerup',{clientX:20,timeStamp:250});
  assert.equal(f.cancelled,1);
  f.emit('pointerdown');
  f.emit('pointermove',{pointerId:2,clientX:100,timeStamp:50});
  f.emit('pointermove',{clientX:-100,timeStamp:100});
  f.emit('pointerup',{clientX:-100,timeStamp:110});
  assert.deepEqual(f.releases,['pass']);
});
test('preview controls remain tappable and page blur cancels an active drag', () => {
  const f=fixture();
  f.emit('pointerdown',{target:{closest:()=>({})}});
  assert.deepEqual(f.active,[]);
  f.emit('pointerdown');f.controller.cancel();
  assert.equal(f.cancelled,1);
  assert.deepEqual(f.releases,[]);
});

test('horizontal drags starting in the description swipe in either direction', () => {
  for (const direction of [-1, 1]) {
    const f=fixture({scrollable:true});
    f.emit('pointerdown');
    f.emit('lostpointercapture'); // transfer from description to card must be safe
    f.emit('pointermove',{clientX:direction*100,clientY:12,timeStamp:100});
    f.emit('pointerup',{clientX:direction*100,clientY:12,timeStamp:110});
    assert.deepEqual(f.releases,[direction>0?'keep':'pass']);
    assert.equal(f.cancelled,0);
  }
});
test('vertical description gestures release the card and cannot later commit', () => {
  const f=fixture({scrollable:true});f.emit('pointerdown');
  f.emit('pointermove',{clientX:4,clientY:30,timeStamp:50});
  f.emit('pointermove',{clientX:110,clientY:35,timeStamp:100});
  f.emit('pointerup',{clientX:110,clientY:35,timeStamp:110});
  assert.equal(f.cancelled,1);
  assert.deepEqual(f.moves,[]);
  assert.deepEqual(f.releases,[]);
  assert.equal(f.card.hasPointerCapture(1),false);
});
test('small diagonal movement does not steal a later horizontal description swipe', () => {
  const f=fixture({scrollable:true});f.emit('pointerdown');
  f.emit('pointermove',{clientX:3,clientY:5,timeStamp:20});
  f.emit('pointermove',{clientX:12,clientY:11,timeStamp:40});
  assert.deepEqual(f.moves,[]);
  f.emit('pointermove',{clientX:100,clientY:15,timeStamp:100});
  f.emit('pointerup',{clientX:100,clientY:15,timeStamp:110});
  assert.deepEqual(f.releases,['keep']);
});
