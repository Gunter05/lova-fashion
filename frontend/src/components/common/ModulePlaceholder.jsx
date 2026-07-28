/**
 * ModulePlaceholder
 *
 * Generic "coming soon" card for modules not yet integrated.
 *
 * @param {number} moduleNumber - The module number (1–7)
 * @param {string} moduleName   - Human-readable module name
 */
export default function ModulePlaceholder({ moduleNumber, moduleName }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 px-10 py-12 flex flex-col items-center gap-4 max-w-sm w-full text-center">
        {/* Module badge */}
        <div className="w-16 h-16 rounded-full bg-rose-50 border-2 border-rose-200 flex items-center justify-center">
          <span className="text-2xl font-extrabold text-rose-400">{moduleNumber}</span>
        </div>

        {/* Module name */}
        <h2 className="text-lg font-semibold text-gray-800">{moduleName}</h2>

        {/* Status chip */}
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          Coming soon
        </span>

        <p className="text-sm text-gray-500 leading-relaxed">
          Module {moduleNumber} is under development and will be available soon.
        </p>
      </div>
    </div>
  );
}
