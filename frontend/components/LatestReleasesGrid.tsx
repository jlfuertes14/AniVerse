"use client";

import { useState, useEffect } from "react";
import { getLatestReleases } from "@/lib/api";
import type { LatestRelease } from "@/lib/types";
import LoadingLink from "@/components/LoadingLink";

interface LatestReleasesGridProps {
    initialReleases: LatestRelease[];
}

export default function LatestReleasesGrid({ initialReleases }: LatestReleasesGridProps) {
    const [releases, setReleases] = useState<LatestRelease[]>(initialReleases);
    const [provider, setProvider] = useState<string>("animepahe");
    const [isLoading, setIsLoading] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);
    const itemsPerPage = 12;

    useEffect(() => {
        if (provider === "animepahe" && releases === initialReleases) return;
        
        async function fetchNewReleases() {
            setIsLoading(true);
            try {
                const data = await getLatestReleases(provider);
                setReleases(data);
                setCurrentPage(1);
            } catch (error) {
                console.error("Failed to fetch releases:", error);
            } finally {
                setIsLoading(false);
            }
        }
        
        fetchNewReleases();
    }, [provider]);

    if (!releases || releases.length === 0) {
        if (isLoading) return <div className="container-wide py-20 text-center">Loading releases...</div>;
        return null;
    }

    // Pagination logic
    const totalPages = Math.ceil(releases.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const currentItems = releases.slice(startIndex, startIndex + itemsPerPage);

    const handlePageChange = (newPage: number) => {
        setCurrentPage(newPage);
        // Scroll to top of section
        const section = document.querySelector(".latest-releases-section");
        if (section) {
            const offset = 100; // Offset for navbar
            const elementPosition = section.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - offset;
            
            window.scrollTo({
                top: offsetPosition,
                behavior: "smooth"
            });
        }
    };

    return (
        <section className="latest-releases-section container-wide">
            <div className="section-header-flex" style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center', 
                marginBottom: '2rem',
                borderBottom: '1px solid var(--border-subtle)',
                paddingBottom: '0.75rem',
                flexWrap: 'wrap',
                gap: '1rem'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                    <h2 className="section-heading" style={{ margin: 0 }}>Latest Releases</h2>
                    
                    <div className="provider-toggle" style={{ 
                        display: 'flex', 
                        background: 'rgba(255,255,255,0.05)', 
                        padding: '3px',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-subtle)'
                    }}>
                        <button 
                            onClick={() => setProvider("animepahe")}
                            style={{
                                padding: '0.4rem 1rem',
                                fontSize: '0.8rem',
                                fontWeight: '600',
                                borderRadius: 'var(--radius-sm)',
                                background: provider === "animepahe" ? 'var(--gold)' : 'transparent',
                                color: provider === "animepahe" ? '#000' : 'var(--text-secondary)',
                                border: 'none',
                                cursor: 'pointer',
                                transition: 'all 0.2s ease'
                            }}
                        >
                            AnimePahe
                        </button>
                        <button 
                            onClick={() => setProvider("reanime")}
                            style={{
                                padding: '0.4rem 1rem',
                                fontSize: '0.8rem',
                                fontWeight: '600',
                                borderRadius: 'var(--radius-sm)',
                                background: provider === "reanime" ? 'var(--gold)' : 'transparent',
                                color: provider === "reanime" ? '#000' : 'var(--text-secondary)',
                                border: 'none',
                                cursor: 'pointer',
                                transition: 'all 0.2s ease'
                            }}
                        >
                            Re:ANIME
                        </button>
                    </div>
                </div>
                {totalPages > 1 && (
                    <div className="pagination-info" style={{ 
                        fontSize: '0.9rem', 
                        fontWeight: '500',
                        color: 'var(--text-secondary)',
                        background: 'var(--bg-surface)',
                        padding: '0.3rem 0.8rem',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-subtle)'
                    }}>
                        Page {currentPage} of {totalPages}
                    </div>
                )}
            </div>

            <div className={`latest-grid ${isLoading ? 'opacity-50 pointer-events-none' : ''}`} style={{ transition: 'opacity 0.3s ease' }}>
                {currentItems.map((rel: LatestRelease, idx: number) => (
                    <div key={`${rel.session || rel.slug || idx}-${idx}`} className="latest-card-wrapper">
                        {rel.mal_id ? (
                            <LoadingLink
                                href={`/watch/${rel.mal_id}/${rel.episode}?from=latest&prefer=${provider}`}
                                className="latest-card"
                                loadingMessage={`Loading ${rel.title}...`}
                            >
                                <div className="latest-image-wrapper">
                                    <img src={rel.snapshot} alt={rel.title} loading="lazy" />
                                    <div className="latest-card-overlay">
                                        <div className="latest-header-row">
                                            <p className="latest-title">{rel.title}</p>
                                            <span className="latest-episode-number">{rel.display_episode || rel.episode}</span>
                                        </div>
                                    </div>
                                </div>
                            </LoadingLink>
                        ) : (
                            <div className="latest-card disabled">
                                <div className="latest-image-wrapper">
                                    <img src={rel.snapshot} alt={rel.title} loading="lazy" />
                                    <div className="latest-card-overlay">
                                        <div className="latest-header-row">
                                            <p className="latest-title">{rel.title}</p>
                                            <span className="latest-episode-number">{rel.display_episode || rel.episode}</span>
                                        </div>
                                        <span className="latest-status-badge">Mapping...</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {totalPages > 1 && (
                <div className="pagination-container" style={{
                    marginTop: '4rem',
                    padding: '2rem 0',
                    borderTop: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '1rem'
                }}>
                    <div className="pagination-bar" style={{ 
                        display: 'flex', 
                        justifyContent: 'center', 
                        alignItems: 'center', 
                        gap: '0.75rem', 
                    }}>
                        <button 
                            onClick={() => handlePageChange(currentPage - 1)}
                            disabled={currentPage === 1}
                            className={`page-btn ${currentPage === 1 ? 'disabled' : ''}`}
                            style={{
                                width: '40px',
                                height: '40px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border-subtle)',
                                borderRadius: 'var(--radius-md)',
                                color: currentPage === 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                                opacity: currentPage === 1 ? 0.5 : 1,
                                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                                transition: 'all 0.2s ease'
                            }}
                            title="Previous Page"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M15 18l-6-6 6-6" />
                            </svg>
                        </button>
                        
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            {[...Array(totalPages)].map((_, i) => {
                                const pageNum = i + 1;
                                
                                if (
                                    totalPages > 5 && 
                                    pageNum !== 1 && 
                                    pageNum !== totalPages && 
                                    (pageNum < currentPage - 1 || pageNum > currentPage + 1)
                                ) {
                                    if (pageNum === currentPage - 2 || pageNum === currentPage + 2) {
                                        return <span key={pageNum} style={{ color: 'var(--text-muted)', alignSelf: 'center', padding: '0 0.25rem' }}>...</span>;
                                    }
                                    return null;
                                }

                                return (
                                    <button
                                        key={pageNum}
                                        onClick={() => handlePageChange(pageNum)}
                                        className={`page-num-btn ${currentPage === pageNum ? 'active' : ''}`}
                                        style={{
                                            width: '40px',
                                            height: '40px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            borderRadius: 'var(--radius-md)',
                                            background: currentPage === pageNum ? 'var(--gold)' : 'var(--bg-surface)',
                                            color: currentPage === pageNum ? '#000' : 'var(--text-primary)',
                                            border: '1px solid',
                                            borderColor: currentPage === pageNum ? 'var(--gold)' : 'var(--border-subtle)',
                                            fontWeight: '700',
                                            fontSize: '0.9rem',
                                            transition: 'all 0.2s ease',
                                            boxShadow: currentPage === pageNum ? '0 0 15px var(--gold-glow)' : 'none'
                                        }}
                                    >
                                        {pageNum}
                                    </button>
                                );
                            })}
                        </div>

                        <button 
                            onClick={() => handlePageChange(currentPage + 1)}
                            disabled={currentPage === totalPages}
                            className={`page-btn ${currentPage === totalPages ? 'disabled' : ''}`}
                            style={{
                                width: '40px',
                                height: '40px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border-subtle)',
                                borderRadius: 'var(--radius-md)',
                                color: currentPage === totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                                opacity: currentPage === totalPages ? 0.5 : 1,
                                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                                transition: 'all 0.2s ease'
                            }}
                            title="Next Page"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M9 18l6-6-6-6" />
                            </svg>
                        </button>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        Showing {startIndex + 1}-{Math.min(startIndex + itemsPerPage, releases.length)} of {releases.length} releases
                    </div>
                </div>
            )}
        </section>
    );
}
