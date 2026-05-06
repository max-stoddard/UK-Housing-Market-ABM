package housing;

public class RentalAgreement extends PaymentAgreement {
    Household landlord;

    void invalidateLandlordRentalIncome() {
        if (landlord != null) {
            landlord.invalidateMonthlyGrossRentalIncome();
        }
    }
}
