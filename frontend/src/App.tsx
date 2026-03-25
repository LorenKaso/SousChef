import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar';
import AllRecipesPage from './pages/AllRecipesPage';
import FavoritesPage from './pages/FavoritesPage';
import RecipeDetailPage from './pages/RecipeDetailPage';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#FAF8F4]">
        <Navbar />
        <Routes>
          <Route path="/" element={<AllRecipesPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
          {/* Catch-all redirects to home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
