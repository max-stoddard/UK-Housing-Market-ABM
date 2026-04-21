package utilities;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PdfTest {

    @Test
    void constructorTrimsLeadingAndTrailingZeroBins() {
        BinnedDataDouble data = binnedData(0.0, 1.0, 0.0, 0.0, 0.2, 0.3, 0.5, 0.0, 0.0);

        Pdf pdf = new Pdf(data);

        assertAll(
                () -> assertEquals(Pdf.DEFAULT_CDF_SAMPLES, pdf.nSamples),
                () -> assertEquals(2.0, pdf.getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, pdf.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(0.2, pdf.density(2.5), 1.0e-12),
                () -> assertEquals(0.5, pdf.density(4.5), 1.0e-12)
        );
    }

    @Test
    void explicitSetPdfOverloadKeepsZeroDensityOutsideTrimmedSupport() {
        BinnedDataDouble data = binnedData(10.0, 0.5, 0.0, 0.1, 0.4, 0.5, 0.0);
        Pdf pdf = new Pdf(0.0, 1.0, x -> 1.0, 17);

        pdf.setPdf(data, 257);

        assertAll(
                () -> assertEquals(257, pdf.nSamples),
                () -> assertEquals(10.5, pdf.getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(12.0, pdf.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(0.0, pdf.density(10.49), 1.0e-12),
                () -> assertEquals(0.0, pdf.density(12.0), 1.0e-12),
                () -> assertEquals(0.0, pdf.density(50.0), 1.0e-12),
                () -> assertEquals(0.2, pdf.density(10.75), 1.0e-12),
                () -> assertEquals(1.0, pdf.density(11.75), 1.0e-12)
        );
    }

    @Test
    void allZeroBinnedDataThrowsIllegalStateException() {
        BinnedDataDouble data = binnedData(-1.0, 0.25, 0.0, 0.0, 0.0, 0.0);

        assertThrows(IllegalStateException.class, () -> new Pdf(data));
    }

    @Test
    void inverseCumulativeProbabilityMatchesAnalyticDistribution() {
        Pdf pdf = new Pdf(0.0, 1.0, x -> 2.0*x, 20001);

        assertAll(
                () -> assertEquals(0.2, pdf.inverseCumulativeProbability(0.04), 5.0e-4),
                () -> assertEquals(0.5, pdf.inverseCumulativeProbability(0.25), 5.0e-4),
                () -> assertEquals(0.9, pdf.inverseCumulativeProbability(0.81), 5.0e-4)
        );
    }

    private static BinnedDataDouble binnedData(double firstBinMin, double binWidth, double... bins) {
        BinnedDataDouble data = new BinnedDataDouble(firstBinMin, binWidth);

        for(double bin : bins) {
            data.add(bin);
        }

        return(data);
    }
}
