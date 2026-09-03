import { NavLink } from 'react-router-dom';

export default function Navbar() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
      'text-sm font-semibold pb-0.5 border-b-2 transition-colors duration-150',
      isActive
        ? 'border-green-600 text-green-700'
        : 'border-transparent text-stone-500 hover:text-stone-800 hover:border-stone-300',
    ].join(' ');

  return (
    <header className="bg-white border-b border-stone-200 sticky top-0 z-10 shadow-sm">
      <div className="max-w-5xl mx-auto px-6 h-20 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-2 select-none">
          {/* Icon — primary visual anchor */}
          <img
            src="/icon.png"
            alt="SousChef logo"
            className="h-[72px] w-[72px] object-contain drop-shadow-lg flex-shrink-0"
          />
          {/* Wordmark — secondary */}
          <div className="flex flex-col justify-center gap-0.5 leading-none">
            <span className="font-semibold text-base text-green-700 tracking-tight">SousChef</span>
            <span className="text-[9px] font-medium text-stone-400 tracking-[0.18em] uppercase">
              Hands-Free Cooking
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex items-center gap-7" aria-label="Main navigation">
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
