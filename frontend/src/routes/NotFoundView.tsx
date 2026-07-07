import { Link } from "react-router-dom";

export default function NotFoundView() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <div className="text-center">
        <h1 className="text-9xl font-bold text-slate-700">404</h1>
        <p className="text-2xl text-slate-400 mt-4 mb-8">Página no encontrada</p>
        <Link
          to="/"
          className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium transition"
        >
          Volver al inicio
        </Link>
      </div>
    </div>
  );
}
