/* Pointer lifecycle and thresholds shared by the UI and regression tests. */
const Swipe = {
  choice(dx, dy, width, velocity) {
    if (Math.abs(dx) <= Math.abs(dy) * 1.2) return null;
    const threshold = Math.min(90, width * 0.23);
    const flick = Math.abs(dx) >= 32 && Math.abs(velocity) >= 0.5 && Math.sign(velocity) === Math.sign(dx);
    return Math.abs(dx) >= threshold || flick ? (dx > 0 ? 'keep' : 'pass') : null;
  },
  attach(card, {canStart, isScrollTarget = () => false, onActive, onMove, onRelease, onCancel}) {
    let active = null;
    function cancel() {
      if (!active) return;
      const id = active.id;
      active = null;
      onActive(false);
      if (card.hasPointerCapture(id)) card.releasePointerCapture(id);
      onCancel();
    }
    card.addEventListener('pointerdown', e => {
      if (active || !e.isPrimary || e.button !== 0 || !canStart(e)) return;
      active = {id:e.pointerId, x:e.clientX, y:e.clientY, lastX:e.clientX, lastTime:e.timeStamp, velocity:0, dragging:false, scrollable:isScrollTarget(e)};
      // Capture on the card immediately, before moves; implicit touch capture may
      // initially belong to a child such as the thumbnail or title.
      card.setPointerCapture(e.pointerId);
      onActive(true);
    });
    card.addEventListener('pointermove', e => {
      if (!active || active.id !== e.pointerId) return;
      const dx = e.clientX - active.x, dy = e.clientY - active.y;
      if (!active.dragging && active.scrollable) {
        // Leave vertical intent to native text scrolling. Horizontal intent
        // locks to the card, even if the gesture began over its description.
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 8) return;
        if (Math.abs(dy) > Math.abs(dx) * 1.15) {cancel(); return;}
        if (Math.abs(dx) <= Math.abs(dy) * 1.15) return;
      }
      if (!active.dragging && Math.abs(dx) < 5) return;
      active.dragging = true;
      const dt = e.timeStamp - active.lastTime;
      if (dt > 0) active.velocity = (e.clientX - active.lastX) / dt;
      active.lastX = e.clientX;
      active.lastTime = e.timeStamp;
      onMove(dx, dy);
    });
    card.addEventListener('pointerup', e => {
      if (!active || active.id !== e.pointerId) return;
      const p = active;
      active = null;
      onActive(false);
      if (card.hasPointerCapture(e.pointerId)) card.releasePointerCapture(e.pointerId);
      const velocity = e.timeStamp - p.lastTime < 100 ? p.velocity : 0;
      const choice = p.dragging ? Swipe.choice(e.clientX - p.x, e.clientY - p.y, card.clientWidth, velocity) : null;
      if (choice) onRelease(choice); else onCancel();
    });
    card.addEventListener('pointercancel', e => {if (active?.id === e.pointerId) cancel();});
    card.addEventListener('lostpointercapture', e => {
      // A child's capture-loss event bubbles. It does not mean the card lost capture.
      if (e.target === card && active?.id === e.pointerId) cancel();
    });
    card.addEventListener('dragstart', e => e.preventDefault());
    return {cancel};
  }
};
if (typeof module !== 'undefined') module.exports = Swipe;
