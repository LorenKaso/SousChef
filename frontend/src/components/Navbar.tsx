import { NavLink } from 'react-router-dom';

export default function Navbar() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
      'text-sm font-medium pb-0.5 border-b-2 transition-colors duration-150',
      isActive
        ? 'border-amber-500 text-stone-900'
        : 'border-transparent text-stone-500 hover:text-stone-800 hover:border-stone-300',
    ].join(' ');

  return (
    <header className="bg-white border-b border-stone-200 sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Brand */}
        <span className="font-bold text-xl text-stone-800 tracking-tight select-none">
          🍳 SousChef
        </span>

        {/* Navigation */}
        <nav className="flex items-center gap-6" aria-label="Main navigation">
          <NavLink to="/" end className={linkClass}>
            All Recipes
          </NavLink>
          <NavLink to="/favorites" className={linkClass}>
            Favorites
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
