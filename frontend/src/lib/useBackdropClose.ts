/**
 * Pop-up arka planına tıklayınca kapat — ama yalnız basma VE bırakma ikisi de
 * arka plandaysa (1.23 A1). Alan içinde fareyle sürükleyip seçerken bırakma
 * pencere dışına taşarsa tarayıcı `click`'i ortak ataya (arka plan) gönderir;
 * önceden bu pop-up'ı kapatıyordu.
 */
import { useRef, type MouseEvent } from "react";

export function useBackdropClose(onClose: () => void) {
  const downOnBackdrop = useRef(false);
  return {
    onMouseDown: (e: MouseEvent<HTMLElement>) => {
      downOnBackdrop.current = e.target === e.currentTarget;
    },
    onClick: (e: MouseEvent<HTMLElement>) => {
      const close = downOnBackdrop.current && e.target === e.currentTarget;
      downOnBackdrop.current = false;
      if (close) onClose();
    },
  };
}
