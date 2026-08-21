import { A2uiSurface, type A2uiSurfaceModel } from "../../lib/agui";

export default function ActiveSurfaceSlot({ surface }: { surface: A2uiSurfaceModel }) {
  return (
    <div className="active-surface-slot" role="dialog" aria-modal="false">
      <A2uiSurface surface={surface} />
    </div>
  );
}
