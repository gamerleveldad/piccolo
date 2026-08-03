import React, { useState, useEffect } from 'react';

export default function GooglePhotosWidget({ apiBase }) {
  const [photos, setPhotos] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const fetchPhotos = async () => {
      try {
        const res = await fetch(`${apiBase}/api/photos`);
        if (res.ok) {
          const data = await res.json();
          const fullUrls = (data.urls || []).map(url => `${apiBase}${encodeURI(url)}`);
          setPhotos(fullUrls);
        }
      } catch (err) {
        console.error("Photos API Fetch Blocked/Failed", err);
      }
    };
    fetchPhotos();
    const interval = setInterval(fetchPhotos, 45 * 60 * 1000); 
    return () => clearInterval(interval);
  }, [apiBase]);

  useEffect(() => {
    if (photos.length <= 1) return;
    const timer = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % photos.length);
    }, 15000);
    return () => clearInterval(timer);
  }, [photos]);

  if (photos.length === 0) {
    return (
      <div className="h-full w-full flex items-center justify-center border border-slate-900/40 rounded-2xl bg-slate-950 shadow-2xl">
        <span className="text-[10px] text-slate-600 font-mono uppercase tracking-widest animate-pulse">
          Awaiting Photo Stream...
        </span>
      </div>
    );
  }

  return (
    <div className="h-full w-full rounded-2xl overflow-hidden border border-slate-900/40 shadow-2xl relative bg-slate-950">
      <img 
        key={photos[currentIndex]}
        src={photos[currentIndex]}
        className="w-full h-full object-cover transition-opacity duration-1000" 
        alt="Display Board" 
      />
      <div className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/50 backdrop-blur-sm rounded text-[8px] font-mono text-slate-400">
        {currentIndex + 1} / {photos.length}
      </div>
    </div>
  );
}